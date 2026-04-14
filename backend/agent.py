"""
agent.py — OpenDev AI production agent (v4)
See full docstring in repo_analyzer.py and pr_reviewer.py for capability details.
"""
from __future__ import annotations
import json, logging, os, re, shutil, tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
from config import Settings
from executor import CommandExecutionError, CommandRunner
from github_service import GitHubService
from llm import LLMError, LLMService
from repo_analyzer import analyze_repository
from rl_agent import RLAgent
from reward import calculate_reward, describe_reward, estimate_immediate_reward
from rules import build_action_context, get_actions, sort_findings_by_priority
from scanner import calculate_security_score, scan_repository
from secret_scanner import scan_secrets

logger = logging.getLogger(__name__)

IGNORED_DIRS = {".git",".next",".venv","__pycache__","build","coverage","dist","node_modules","venv"}
TEXT_EXTS = {".c",".cpp",".css",".go",".java",".js",".json",".jsx",".md",".py",".rb",".rs",".sh",".ts",".tsx",".txt",".toml",".yaml",".yml"}
SECURITY_PATTERNS = {
    "aws_access_key":    re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token":      re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "slack_token":       re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "private_key_header":re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----"),
    "generic_secret":    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|client_secret|access_token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-\/+=]{8,}"),
}

@dataclass(slots=True)
class PendingAction:
    kind: str; branch_name: str; base_branch: str; commit_message: str
    pr_title: str; pr_body: str; repo_path: str
    temp_dir: tempfile.TemporaryDirectory
    diff: str; summary: str
    issue_number: int | None = None
    findings: list[dict[str,Any]] = field(default_factory=list)
    test_results: list[dict[str,Any]] = field(default_factory=list)
    fork_full_name: str | None = None; fork_owner: str | None = None
    rl_action: str | None = None; rl_state: dict[str,str] | None = None
    reward_info: dict[str,Any] | None = None

@dataclass(slots=True)
class SessionState:
    session_id: str; repo_url: str; repo: dict[str,Any]; issues: list[dict[str,Any]]
    repo_analysis: dict[str,Any] | None = None
    logs: list[dict[str,Any]] = field(default_factory=list)
    last_result: dict[str,Any] | None = None; pending_action: PendingAction | None = None
    last_security_score: dict[str,Any] | None = None
    last_scan_findings: list[dict[str,Any]] = field(default_factory=list)

class AgentError(RuntimeError): pass

class OpenDevAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = CommandRunner(timeout_seconds=settings.command_timeout_seconds)
        self.github = GitHubService(settings.github_token, self.runner, author_name=settings.git_author_name, author_email=settings.git_author_email)
        self.llm = LLMService(settings)
        self.rl = RLAgent()
        self.sessions: dict[str, SessionState] = {}
        self.lock = Lock()

    def create_repo_session(self, repo_url: str) -> dict[str, Any]:
        self._require_github()
        repo = self.github.get_repository_details(repo_url)
        issues = self.github.get_open_issues(repo_url)
        session_id = uuid4().hex
        state = SessionState(session_id=session_id, repo_url=repo_url, repo=repo, issues=issues)
        self._log(state, "info", "repo", f"Loaded {repo['full_name']} — {len(issues)} open issues.")
        repo_analysis: dict[str, Any] = {}
        try:
            with tempfile.TemporaryDirectory(prefix="opendev-analyze-") as td:
                rp = Path(td) / "repo"
                self._log(state, "info", "analyze", "Cloning for code analysis…")
                self.github.clone_repository(repo_url, rp)
                repo_analysis = analyze_repository(rp)
                self._log(state, "info", "analyze",
                    f"Detected: {repo_analysis.get('project_type')} | {repo_analysis.get('primary_language')} | "
                    f"Frameworks: {', '.join(repo_analysis.get('frameworks', []) or ['none detected'])}")
        except Exception as exc:
            self._log(state, "warn", "analyze", f"Analysis skipped: {exc}")
        state.repo_analysis = repo_analysis
        with self.lock:
            self.sessions[session_id] = state
        return {"session_id": session_id, "repo": repo, "issues": issues,
                "repo_analysis": repo_analysis, "logs": state.logs, "has_issues": len(issues) > 0}

    def get_issues(self, session_id: str) -> dict[str, Any]:
        state = self._get_session(session_id)
        return {"session_id": session_id, "issues": state.issues, "repo": state.repo, "repo_analysis": state.repo_analysis}

    def get_logs(self, session_id: str) -> dict[str, Any]:
        state = self._get_session(session_id)
        return {"session_id": session_id, "logs": state.logs, "pending_action": state.pending_action is not None}

    def terminate_session(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            state = self.sessions.pop(session_id, None)
        if not state:
            raise AgentError("Session not found.")
        self._clear_pending_action(state)
        return {"session_id": session_id, "status": "terminated"}

    def fork_and_fix_issue(self, session_id: str, issue_number: int) -> dict[str, Any]:
        self._require_llm()
        state = self._get_session(session_id)
        issue = next((i for i in state.issues if i["number"] == issue_number), None)
        if not issue:
            raise AgentError(f"Issue #{issue_number} not found.")
        self._clear_pending_action(state)
        self._log(state, "info", "fork", f"Starting fork-fix for issue #{issue_number}.")
        temp_dir = tempfile.TemporaryDirectory(prefix="opendev-fork-")
        repo_path = Path(temp_dir.name) / "repo"
        branch_name = f"opendev/fix-{issue_number}-{uuid4().hex[:8]}"
        try:
            fork_info = self.github.fork_repository(state.repo_url)
            fork_full_name = fork_info["full_name"]; fork_owner = fork_info["owner"]
            self._log(state, "info", "fork", f"Fork: {fork_full_name}")
            fork_url = self.github.get_fork_clone_url(fork_full_name)
            self.runner.run_git(["clone", "--depth", "1", fork_url, str(repo_path)])
            self.github.create_branch(repo_path, branch_name)
            prompt = self._build_issue_prompt(repo_path, state.repo, issue, state.repo_analysis)
            self._log(state, "info", "llm", "Generating fix…")
            llm_result = self.llm.generate_code(prompt)
            payload = llm_result.parsed
            changes = payload.get("changes") or []
            if not changes:
                raise AgentError(payload.get("summary", "LLM returned no changes."))
            touched = self._apply_changes(repo_path, changes)
            diff = self.github.get_diff(repo_path)
            if not diff.strip():
                raise AgentError("Patch produced no diff.")
            test_results = self._run_project_tests(state, repo_path)
            if any(t["status"] == "failed" for t in test_results):
                result = {"action": "fork_fix", "status": "failed", "issue_number": issue_number,
                          "summary": payload.get("summary", "Tests failed."), "diff": diff,
                          "test_results": test_results, "touched_files": touched, "fork": fork_info}
                state.last_result = result; self._cleanup_temp_dir(temp_dir); return result
            commit_msg = payload.get("commit_message") or f"fix: resolve issue #{issue_number}"
            pr_title = payload.get("pr_title") or f"Fix issue #{issue_number}"
            pr_body = payload.get("pr_body") or f"## Summary\n{payload.get('summary','')}\n\nCloses #{issue_number}."
            self.github.commit_all(repo_path, commit_msg)
            self._log(state, "info", "git", f"Commit staged on branch {branch_name}")
            pending = PendingAction(kind="fork_fix", branch_name=branch_name, base_branch=state.repo["default_branch"],
                commit_message=commit_msg, pr_title=pr_title, pr_body=pr_body,
                repo_path=str(repo_path), temp_dir=temp_dir, diff=diff,
                summary=payload.get("summary", f"Fix for #{issue_number}."), issue_number=issue_number,
                test_results=test_results, fork_full_name=fork_full_name, fork_owner=fork_owner)
            state.pending_action = pending
            result = {"action": "fork_fix", "status": "awaiting_approval", "issue_number": issue_number,
                      "summary": pending.summary, "diff": diff, "test_results": test_results,
                      "touched_files": touched, "branch_name": branch_name, "fork": fork_info}
            state.last_result = result
            self._log(state, "info", "approval", "PR staged — awaiting your approval.")
            return result
        except (AgentError, CommandExecutionError, LLMError, RuntimeError, ValueError) as exc:
            self._cleanup_temp_dir(temp_dir); self._log(state, "error", "fork_fix", str(exc))
            raise AgentError(str(exc)) from exc

    def deep_security_scan(self, session_id: str) -> dict[str, Any]:
        self._require_github()
        state = self._get_session(session_id)
        self._clear_pending_action(state)
        self._log(state, "info", "scan", "Starting full security scan…")
        try:
            with tempfile.TemporaryDirectory(prefix="opendev-scan-") as td:
                rp = Path(td) / "repo"
                self.github.clone_repository(state.repo_url, rp)
                self._log(state, "info", "scan", "Scanning for vulnerabilities…")
                vuln_findings = scan_repository(rp)
                self._log(state, "info", "scan", "Scanning for secrets & credentials…")
                secret_findings = scan_secrets(rp)
                all_findings = sort_findings_by_priority(vuln_findings + secret_findings)
                state.last_scan_findings = all_findings
                security_score = calculate_security_score(all_findings)
                state.last_security_score = security_score
                self._log(state, "info", "scan",
                    f"Found {len(vuln_findings)} vulnerabilities + {len(secret_findings)} secrets. "
                    f"Score: {security_score['score']}/100 ({security_score['grade']})")
                result = {"action": "security_scan", "status": "complete",
                    "summary": (f"Security scan complete. Score: {security_score['score']}/100 "
                        f"(Grade {security_score['grade']}). {len(all_findings)} findings."),
                    "vuln_findings": vuln_findings, "secret_findings": secret_findings,
                    "all_findings": all_findings, "security_score": security_score,
                    "diff": "", "create_issues_available": len(all_findings) > 0}
                state.last_result = result
                return result
        except (CommandExecutionError, RuntimeError, ValueError) as exc:
            self._log(state, "error", "scan", str(exc)); raise AgentError(str(exc)) from exc

    def scan_repository(self, session_id: str) -> dict[str, Any]:
        return self.deep_security_scan(session_id)

    def create_issues_from_findings(self, session_id: str, finding_ids: list[int] | None = None) -> dict[str, Any]:
        self._require_github()
        state = self._get_session(session_id)
        if not state.last_scan_findings:
            raise AgentError("No scan findings — run security scan first.")
        findings = state.last_scan_findings
        if finding_ids:
            findings = [f for f in findings if f.get("id") in finding_ids]
        else:
            findings = [f for f in findings if f.get("severity") in ("high", "medium")]
        if not findings:
            return {
                "status": "nothing_to_create",
                "created": [],
                "errors": [],
                "issues_created": 0,
                "total_findings": len(state.last_scan_findings),
            }
        self._log(state, "info", "create_issues", f"Opening {len(findings)} GitHub issues…")
        created: list[dict[str,Any]] = []; errors: list[str] = []
        for finding in findings:
            try:
                issue = self.github.create_issue_from_finding(state.repo_url, finding)
                created.append({"finding": finding, "issue": issue})
                self._log(state, "info", "create_issues", f"Created #{issue['number']}: {issue['title'][:60]}")
            except Exception as exc:
                err = f"Failed for {finding.get('type')}: {exc}"; errors.append(err)
                self._log(state, "warn", "create_issues", err)
        return {"status": "ok", "created": created, "errors": errors,
                "issues_created": len(created), "total_findings": len(state.last_scan_findings)}

    def review_pull_request(self, session_id: str, repo_url: str, pr_number: int, post_comment: bool = False) -> dict[str, Any]:
        self._require_llm()
        state = self._get_session(session_id)
        self._log(state, "info", "pr_review", f"Reviewing PR #{pr_number} in {repo_url}…")
        from pr_reviewer import fetch_pr_details, build_review_prompt, post_review_comment
        try:
            pr_details = fetch_pr_details(self.settings.github_token, repo_url, pr_number)
            self._log(state, "info", "pr_review", f"PR: {pr_details['title']} (+{pr_details['additions']} -{pr_details['deletions']})")
            prompt = build_review_prompt(pr_details)
            llm_result = self.llm.generate_code(prompt)
            review = llm_result.parsed
            review.setdefault("recommendation", "COMMENT"); review.setdefault("issues", [])
            review.setdefault("positives", []); review.setdefault("summary", "Review complete.")
            review.setdefault("confidence", 0.7)
            self._log(state, "info", "pr_review", f"Recommendation: {review['recommendation']}")
            post_result: dict[str,Any] = {}
            if post_comment and review.get("review_comment"):
                post_result = post_review_comment(self.settings.github_token, repo_url, pr_number,
                    review["review_comment"], review["recommendation"])
                if post_result.get("posted"):
                    self._log(state, "info", "pr_review", "Review posted to GitHub.")
            return {"pr_details": pr_details, "review": review, "post_result": post_result}
        except Exception as exc:
            self._log(state, "error", "pr_review", str(exc)); raise AgentError(str(exc)) from exc

    def approve(self, session_id: str, approved: bool) -> dict[str, Any]:
        state = self._get_session(session_id)
        if not state.pending_action:
            raise AgentError("No pending action.")
        pending = state.pending_action
        if not approved:
            self._log(state, "info", "approval", "Rejected — branch discarded.")
            if pending.rl_state and pending.rl_action:
                rv, _ = calculate_reward({"tests_passed": False, "build_failed": False, "issue_fixed": False, "no_change": True})
                self.rl.update(pending.rl_state, pending.rl_action, rv)
            self._clear_pending_action(state)
            state.last_result = {"action": pending.kind, "status": "rejected", "summary": "Rejected.",
                                  "diff": pending.diff, "findings": pending.findings, "test_results": pending.test_results}
            return state.last_result
        try:
            repo_path = Path(pending.repo_path)
            if pending.fork_full_name:
                self._log(state, "info", "git", f"Pushing to fork {pending.fork_full_name}…")
                self.github.add_fork_remote(repo_path, pending.fork_full_name)
                self.github.push_to_fork(repo_path, pending.branch_name)
                head = f"{pending.fork_owner}:{pending.branch_name}"
            else:
                self.github.push_branch(repo_path, pending.branch_name)
                head = pending.branch_name
            pr = self.github.create_pull_request(state.repo_url, title=pending.pr_title, body=pending.pr_body, head=head, base=pending.base_branch)
            self._log(state, "info", "pr", f"PR #{pr['number']} created: {pr['url']}")
            if pending.rl_state and pending.rl_action:
                tests_ok = all(t["status"] in ("passed","skipped") for t in pending.test_results)
                rv, ri = calculate_reward({"tests_passed": tests_ok, "build_failed": False, "issue_fixed": True, "secret_removed": pending.kind in ("scan","autonomous")})
                self.rl.update(pending.rl_state, pending.rl_action, rv)
                pending.reward_info = ri
            state.last_result = {"action": pending.kind, "status": "approved", "summary": pending.summary,
                                  "diff": pending.diff, "findings": pending.findings, "test_results": pending.test_results,
                                  "pull_request": pr, "reward_info": pending.reward_info, "fork_full_name": pending.fork_full_name}
            self._clear_pending_action(state)
            return state.last_result
        except (CommandExecutionError, RuntimeError, ValueError) as exc:
            self._log(state, "error", "approval", str(exc)); raise AgentError(str(exc)) from exc

    def fix_issue(self, session_id: str, issue_number: int) -> dict[str, Any]:
        return self.fork_and_fix_issue(session_id, issue_number)

    def get_security_score(self, session_id: str) -> dict[str, Any]:
        state = self._get_session(session_id)
        return {"session_id": session_id, "security_score": state.last_security_score}

    def get_rl_stats(self) -> dict[str, Any]:
        return {"stats": self.rl.get_stats(), "policy": self.rl.get_policy_table()}

    def _require_github(self) -> None:
        if self.settings.missing_github:
            raise AgentError(f"Missing: {', '.join(self.settings.missing_github)}")

    def _require_llm(self) -> None:
        self._require_github()
        if not self.settings.has_llm_provider:
            raise AgentError("No LLM provider configured.")

    def _get_session(self, session_id: str) -> SessionState:
        with self.lock:
            state = self.sessions.get(session_id)
        if not state:
            raise AgentError("Session not found. Reload the home page.")
        return state

    def _log(self, state: SessionState, level: str, step: str, message: str) -> None:
        state.logs.append({"timestamp": datetime.now(timezone.utc).isoformat(), "level": level, "step": step, "message": message})
        fn = getattr(logger, level if level in ("debug","info","warning","error") else "info")
        fn("[%s] %s", step, message)

    def _clear_pending_action(self, state: SessionState) -> None:
        if state.pending_action:
            self._cleanup_temp_dir(state.pending_action.temp_dir); state.pending_action = None

    @staticmethod
    def _cleanup_temp_dir(td: Any) -> None:
        try: td.cleanup()
        except Exception: pass

    def _build_issue_prompt(self, repo_path: Path, repo: dict[str,Any], issue: dict[str,Any], analysis: dict[str,Any] | None) -> str:
        tree = "\n".join(str(p.relative_to(repo_path)) + ("/" if p.is_dir() else "") for p in sorted(repo_path.rglob("*")) if not any(d in IGNORED_DIRS for d in p.relative_to(repo_path).parts))[:4000]
        files = self._relevant_files(repo_path, issue)
        sections = [f"FILE: {fp.relative_to(repo_path)}\n```\n{fp.read_text(encoding='utf-8',errors='ignore')[:5000]}\n```" for fp in files]
        ctx = f"\nStack: {', '.join(analysis.get('tech_stack',[]))}\nLanguage: {analysis.get('primary_language')}" if analysis else ""
        return (f"You are OpenDev AI. Generate a minimal fix. Return JSON ONLY:\n"
                f'{{"summary":"...","commit_message":"...","pr_title":"...","pr_body":"...","changes":[{{"path":"...","action":"update|create|delete","content":"..."}}]}}\n'
                f"Repo: {repo['full_name']}{ctx}\nIssue #{issue['number']}: {issue['title']}\nBody:\n{issue.get('body') or 'No details.'}\nTree:\n{tree}\nFiles:\n{'\\n\\n'.join(sections)}")

    def _relevant_files(self, repo_path: Path, issue: dict[str,Any]) -> list[Path]:
        keywords = set(re.findall(r"[a-zA-Z0-9_]{4,}", f"{issue['title']} {issue.get('body','')}".lower()))
        candidates: list[tuple[int,Path]] = []; fallback: list[Path] = []
        for path in repo_path.rglob("*"):
            if path.is_dir(): continue
            rel = path.relative_to(repo_path)
            if any(p in IGNORED_DIRS for p in rel.parts): continue
            if path.suffix.lower() not in TEXT_EXTS: continue
            if path.stat().st_size > 80_000: continue
            score = sum(3 for kw in keywords if kw in str(rel).lower())
            if path.name in {"README.md","package.json","requirements.txt"}: score += 2
            if score > 0: candidates.append((score, path))
            fallback.append(path)
        selected = [p for _,p in sorted(candidates, key=lambda x: x[0], reverse=True)[:8]]
        for p in fallback:
            if p not in selected: selected.append(p)
            if len(selected) >= 6: break
        return selected[:8]

    def _apply_changes(self, repo_path: Path, changes: list[dict[str,Any]]) -> list[str]:
        touched: list[str] = []
        for change in changes:
            rel = str(change.get("path","")).strip().lstrip("/")
            if not rel: raise AgentError("Change missing file path.")
            target = (repo_path / rel).resolve()
            if repo_path.resolve() not in target.parents and target != repo_path.resolve():
                raise AgentError(f"Unsafe path: {rel}")
            action = str(change.get("action","update")).lower()
            if action == "delete":
                if target.exists(): target.unlink()
                touched.append(rel); continue
            content = change.get("content")
            if not isinstance(content, str): raise AgentError(f"No content for {rel}.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8"); touched.append(rel)
        return touched

    def _run_project_tests(self, state: SessionState, repo_path: Path) -> list[dict[str,Any]]:
        results: list[dict[str,Any]] = []
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            try: pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            except Exception: pkg = {}
            if pkg.get("scripts",{}).get("test"):
                r = self._run_cmd(state, repo_path, ["npm","install"], 900); results.append(r)
                if r["status"] == "passed": results.append(self._run_cmd(state, repo_path, ["npm","test"], 900))
            else: results.append({"command":"npm test","status":"skipped","stdout":"","stderr":"No test script."})
        if any((repo_path/m).exists() for m in ("pyproject.toml","requirements.txt","setup.py","pytest.ini")):
            results.append(self._run_cmd(state, repo_path, ["pytest"], 900))
        if not results: results.append({"command":"tests","status":"skipped","stdout":"","stderr":"No test suite."})
        return results

    def _run_cmd(self, state: SessionState, repo_path: Path, cmd: list[str], timeout: int) -> dict[str,Any]:
        self._log(state, "info", "tests", f"Running {' '.join(cmd)}")
        try:
            r = self.runner.run_repo_command(cmd, cwd=repo_path, timeout=timeout)
            return {"command":" ".join(cmd),"status":"passed","stdout":r.stdout,"stderr":r.stderr}
        except CommandExecutionError as exc:
            return {"command":" ".join(cmd),"status":"failed","stdout":"","stderr":str(exc)}
