"""
github_service.py — GitHub API wrapper for OpenDev AI (production).

New capabilities vs original:
  - fork_repository()          fork a repo into the authed user's account
  - get_fork_url()             return the fork URL for the authed user
  - create_issue()             open a new GitHub issue in the target repo
  - create_issue_from_finding() build a rich issue from a scanner finding
  - get_pr_status()            poll a PR's merge/close state for RL feedback
  - get_issue_status()         poll an issue's open/closed state
  - create_pull_request()      now supports cross-fork head ("owner:branch")
  - push_to_fork()             push a branch to the authenticated fork remote
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from github import Github, GithubException

from executor import CommandRunner

logger = logging.getLogger(__name__)

# Severity → GitHub label colour (hex, no #)
_SEVERITY_COLOURS: dict[str, str] = {
    "high": "d73a4a",
    "medium": "e4a11b",
    "low": "0075ca",
}

# Finding type → sensible GitHub label name
_TYPE_LABELS: dict[str, str] = {
    "sql_injection": "security",
    "xss": "security",
    "unsafe_eval": "security",
    "command_injection": "security",
    "path_traversal": "security",
    "insecure_deserialization": "security",
    "weak_cryptography": "security",
    "aws_access_key": "secret-exposure",
    "github_token": "secret-exposure",
    "generic_password": "secret-exposure",
    "generic_api_key": "secret-exposure",
    "private_key": "secret-exposure",
    "sensitive_file": "secret-exposure",
    "database_url": "secret-exposure",
    "bug": "bug",
    "performance": "performance",
    "documentation": "documentation",
}


class GitHubService:
    def __init__(
        self,
        token: str,
        runner: CommandRunner,
        *,
        author_name: str,
        author_email: str,
    ) -> None:
        self.token = token
        self.client = Github(token) if token else None
        self.runner = runner
        self.author_name = author_name
        self.author_email = author_email
        self._authenticated_user: str | None = None

    # -----------------------------------------------------------------------
    # Repository information
    # -----------------------------------------------------------------------

    def get_repository_details(self, repo_url: str) -> dict:
        repo = self._get_repo(repo_url)
        return {
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "clone_url": repo.clone_url,
            "html_url": repo.html_url,
            "language": repo.language,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "open_issues_count": repo.open_issues_count,
            "is_fork": repo.fork,
            "private": repo.private,
            "topics": list(repo.get_topics()),
        }

    def get_authenticated_user(self) -> str:
        """Return the login name of the token owner (cached)."""
        if not self._authenticated_user:
            if not self.client:
                raise RuntimeError("GitHub client is not configured.")
            self._authenticated_user = self.client.get_user().login
        return self._authenticated_user

    # -----------------------------------------------------------------------
    # Issues
    # -----------------------------------------------------------------------

    def get_open_issues(self, repo_url: str, limit: int = 30) -> list[dict]:
        repo = self._get_repo(repo_url)
        issues: list[dict] = []
        for issue in repo.get_issues(state="open"):
            if issue.pull_request:
                continue
            issues.append({
                "number": issue.number,
                "title": issue.title,
                "body": issue.body or "",
                "url": issue.html_url,
                "labels": [lbl.name for lbl in issue.labels],
                "state": issue.state,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "complexity": self._classify_issue(
                    issue.title,
                    issue.body or "",
                    [lbl.name for lbl in issue.labels],
                ),
            })
            if len(issues) >= limit:
                break
        return issues

    def create_issue(
        self,
        repo_url: str,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict:
        """
        Open a new GitHub issue in the target repository.
        Ensures labels exist before assigning them.
        """
        repo = self._get_repo(repo_url)
        label_objects = []
        for label_name in labels or []:
            label_objects.append(self._ensure_label(repo, label_name))

        issue = repo.create_issue(
            title=title,
            body=body,
            labels=label_objects or [],
        )
        logger.info("create_issue: opened #%d in %s", issue.number, repo.full_name)
        return {
            "number": issue.number,
            "title": issue.title,
            "url": issue.html_url,
            "state": issue.state,
            "labels": [lbl.name for lbl in issue.labels],
        }

    def create_issue_from_finding(self, repo_url: str, finding: dict) -> dict:
        """
        Build a rich, Markdown-formatted GitHub issue from a scanner finding
        and open it in the repository.
        """
        finding_type = finding.get("type", "unknown")
        severity = finding.get("severity", "medium")
        description = finding.get("description", finding_type.replace("_", " ").title())
        file_path = finding.get("file")
        line = finding.get("line")
        preview = finding.get("preview", "")
        fix_types = finding.get("fix_types", [])
        source = finding.get("source", "code")

        # ---- Title --------------------------------------------------------
        location = f"`{file_path}`" if file_path else "repository"
        if line:
            location += f" line {line}"
        title = f"[{severity.upper()}] {description} in {location}"[:200]

        # ---- Body ---------------------------------------------------------
        body_lines = [
            f"## {description}",
            "",
            f"**Severity:** `{severity}`  ",
            f"**Type:** `{finding_type}`  ",
            f"**Source:** `{source}`  ",
        ]
        if file_path:
            body_lines += [f"**File:** `{file_path}`  "]
        if line:
            body_lines += [f"**Line:** `{line}`  "]
        body_lines += [""]

        if preview:
            body_lines += [
                "### Affected code",
                "```",
                preview[:500],
                "```",
                "",
            ]

        if fix_types:
            body_lines += [
                "### Recommended fix strategies",
                *[f"- `{ft}`" for ft in fix_types],
                "",
            ]

        body_lines += [
            "---",
            "_Automatically detected by [OpenDev AI](https://github.com/opendev-ai) security scanner._",
        ]

        # ---- Labels -------------------------------------------------------
        labels_to_add = ["opendev-ai"]
        type_label = _TYPE_LABELS.get(finding_type)
        if type_label:
            labels_to_add.append(type_label)
        if severity in ("high", "medium"):
            labels_to_add.append(f"severity:{severity}")

        return self.create_issue(
            repo_url,
            title=title,
            body="\n".join(body_lines),
            labels=labels_to_add,
        )

    def get_issue_status(self, repo_url: str, issue_number: int) -> dict:
        repo = self._get_repo(repo_url)
        try:
            issue = repo.get_issue(issue_number)
            return {
                "number": issue.number,
                "state": issue.state,
                "title": issue.title,
                "url": issue.html_url,
            }
        except GithubException as exc:
            raise RuntimeError(f"Could not fetch issue #{issue_number}: {exc}") from exc

    # -----------------------------------------------------------------------
    # Fork workflow
    # -----------------------------------------------------------------------

    def fork_repository(self, repo_url: str) -> dict:
        """
        Fork *repo_url* into the authenticated user's account.
        If the fork already exists, return the existing fork details.
        Returns a dict with full_name, clone_url, html_url.
        """
        repo = self._get_repo(repo_url)
        me = self.get_authenticated_user()

        # Check if fork already exists
        existing_fork = self._find_existing_fork(repo, me)
        if existing_fork:
            logger.info("fork_repository: fork already exists at %s", existing_fork.full_name)
            return {
                "full_name": existing_fork.full_name,
                "clone_url": existing_fork.clone_url,
                "html_url": existing_fork.html_url,
                "owner": me,
                "already_existed": True,
            }

        fork = repo.create_fork()
        # GitHub creates forks asynchronously; wait up to 30 s
        for _ in range(15):
            try:
                fork.get_contents("/")
                break
            except GithubException:
                time.sleep(2)

        logger.info("fork_repository: created fork %s", fork.full_name)
        return {
            "full_name": fork.full_name,
            "clone_url": fork.clone_url,
            "html_url": fork.html_url,
            "owner": me,
            "already_existed": False,
        }

    def get_fork_clone_url(self, fork_full_name: str) -> str:
        """Return an authenticated clone URL for a fork."""
        if self.token:
            return f"https://x-access-token:{self.token}@github.com/{fork_full_name}.git"
        return f"https://github.com/{fork_full_name}.git"

    def add_fork_remote(self, repo_path: Path, fork_full_name: str) -> None:
        """Add (or update) the 'fork' remote inside an already-cloned repo."""
        fork_url = self.get_fork_clone_url(fork_full_name)
        try:
            self.runner.run_git(["remote", "add", "fork", fork_url], cwd=repo_path)
        except Exception:
            # Remote may already exist from a previous attempt — update it
            self.runner.run_git(["remote", "set-url", "fork", fork_url], cwd=repo_path)

    def push_to_fork(self, repo_path: Path, branch_name: str) -> None:
        """Push *branch_name* to the 'fork' remote."""
        self.runner.run_git(
            ["push", "fork", branch_name, "--force"],
            cwd=repo_path,
            timeout=900,
        )

    # -----------------------------------------------------------------------
    # Git helpers
    # -----------------------------------------------------------------------

    def clone_repository(self, repo_url: str, destination: Path) -> None:
        clone_url = self._build_clone_url(repo_url)
        self.runner.run_git(["clone", "--depth", "1", clone_url, str(destination)])

    def create_branch(self, repo_path: Path, branch_name: str) -> None:
        self.runner.run_git(["checkout", "-b", branch_name], cwd=repo_path)

    def get_diff(self, repo_path: Path) -> str:
        result = self.runner.run_git(["diff", "--", "."], cwd=repo_path)
        return result.stdout

    def commit_all(self, repo_path: Path, message: str) -> None:
        self.runner.run_git(["config", "user.name", self.author_name], cwd=repo_path)
        self.runner.run_git(["config", "user.email", self.author_email], cwd=repo_path)
        self.runner.run_git(["add", "-A"], cwd=repo_path)
        status = self.runner.run_git(["status", "--porcelain"], cwd=repo_path)
        if not status.stdout:
            raise RuntimeError("No changes were produced.")
        self.runner.run_git(["commit", "-m", message], cwd=repo_path)

    def push_branch(self, repo_path: Path, branch_name: str) -> None:
        """Push to origin (direct push, used when the user owns the repo)."""
        self.runner.run_git(["push", "origin", branch_name], cwd=repo_path, timeout=900)

    # -----------------------------------------------------------------------
    # Pull requests
    # -----------------------------------------------------------------------

    def create_pull_request(
        self,
        repo_url: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        """
        Create a PR.  *head* can be:
          - "branch-name"                     (same repo)
          - "fork-owner:branch-name"          (cross-fork)
        """
        repo = self._get_repo(repo_url)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        logger.info("create_pull_request: PR #%d at %s", pr.number, pr.html_url)
        return {
            "number": pr.number,
            "url": pr.html_url,
            "title": pr.title,
            "state": pr.state,
        }

    def get_pr_status(self, repo_url: str, pr_number: int) -> dict:
        repo = self._get_repo(repo_url)
        try:
            pr = repo.get_pull(pr_number)
            merged = pr.merged
            issue_closed = False
            if merged and pr.body:
                for num_str in re.findall(
                    r"(?:closes?|fixes?|resolves?)\s+#(\d+)", pr.body, re.IGNORECASE
                ):
                    try:
                        linked = repo.get_issue(int(num_str))
                        if linked.state == "closed":
                            issue_closed = True
                            break
                    except GithubException:
                        pass
            return {
                "number": pr.number,
                "state": pr.state,
                "merged": merged,
                "mergeable": pr.mergeable,
                "title": pr.title,
                "url": pr.html_url,
                "issue_closed": issue_closed,
                "review_comments": pr.review_comments,
                "commits": pr.commits,
            }
        except GithubException as exc:
            raise RuntimeError(f"Could not fetch PR #{pr_number}: {exc}") from exc

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _get_repo(self, repo_url: str):
        if not self.client:
            raise RuntimeError("GitHub client is not configured.")
        return self.client.get_repo(self._extract_repo_slug(repo_url))

    def _build_clone_url(self, repo_url: str) -> str:
        slug = self._extract_repo_slug(repo_url)
        if self.token:
            return f"https://x-access-token:{self.token}@github.com/{slug}.git"
        return f"https://github.com/{slug}.git"

    @staticmethod
    def _extract_repo_slug(repo_url: str) -> str:
        parsed = urlparse(repo_url)
        if parsed.netloc not in {"github.com", "www.github.com"}:
            raise ValueError("Only GitHub repository URLs are supported.")
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise ValueError("Invalid GitHub repository URL.")
        return "/".join(parts[:2])

    @staticmethod
    def _classify_issue(title: str, body: str, labels: list[str]) -> str:
        combined = " ".join([title.lower(), body.lower(), " ".join(labels).lower()])
        complex_signals = ("architecture", "migration", "oauth", "database", "performance", "security", "rewrite")
        simple_signals = ("typo", "docs", "readme", "test", "small", "cleanup", "refactor")
        if any(s in combined for s in complex_signals) or len(body) > 1800:
            return "complex"
        if any(s in combined for s in simple_signals) or len(body) < 500:
            return "simple"
        return "medium"

    @staticmethod
    def _find_existing_fork(repo, user_login: str):
        try:
            for fork in repo.get_forks():
                if fork.owner.login == user_login:
                    return fork
        except GithubException:
            pass
        return None

    def _ensure_label(self, repo, label_name: str):
        """Get or create a label on *repo*."""
        try:
            return repo.get_label(label_name)
        except GithubException:
            colour = _SEVERITY_COLOURS.get(
                label_name.replace("severity:", ""), "cccccc"
            )
            try:
                return repo.create_label(label_name, colour)
            except GithubException:
                return label_name  # PyGithub also accepts raw strings
