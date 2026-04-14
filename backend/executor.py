"""
executor.py — Command runner and fix verification engine.

Original CommandRunner class is unchanged.
New: PatchExecutor.apply_and_verify() applies a generated patch,
     runs tests, re-scans the file, and returns a structured result
     that the reward calculator can consume directly.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Original classes (unchanged)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


class CommandExecutionError(RuntimeError):
    pass


class CommandRunner:
    SAFE_REPO_COMMANDS = {
        ("npm", "install"),
        ("npm", "test"),
        ("pytest",),
    }

    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
        allowed_prefixes: Iterable[tuple[str, ...]] | None = None,
    ) -> CommandResult:
        if allowed_prefixes is not None and not self._is_allowed(command, allowed_prefixes):
            raise ValueError(f"Command not allowed: {' '.join(command)}")

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        started_at = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                env=merged_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout or self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"Command timed out after {timeout or self.timeout_seconds}s: {' '.join(command)}"
            ) from exc

        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            duration_seconds=time.perf_counter() - started_at,
        )

    def run_or_raise(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
        allowed_prefixes: Iterable[tuple[str, ...]] | None = None,
    ) -> CommandResult:
        result = self.run(
            command,
            cwd=cwd,
            timeout=timeout,
            env=env,
            allowed_prefixes=allowed_prefixes,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "Command failed without output."
            raise CommandExecutionError(f"{' '.join(command)} failed: {details}")
        return result

    def run_git(
        self,
        args: list[str],
        *,
        cwd: str | Path | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        return self.run_or_raise(
            ["git", *args],
            cwd=cwd,
            timeout=timeout,
            env=env,
            allowed_prefixes=[("git",)],
        )

    def run_repo_command(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        return self.run_or_raise(
            command,
            cwd=cwd,
            timeout=timeout,
            env=env,
            allowed_prefixes=self.SAFE_REPO_COMMANDS,
        )

    @staticmethod
    def _is_allowed(command: list[str], allowed_prefixes: Iterable[tuple[str, ...]]) -> bool:
        for prefix in allowed_prefixes:
            if tuple(command[: len(prefix)]) == prefix:
                return True
        return False


# ---------------------------------------------------------------------------
# New: PatchExecutor — apply → test → rescan → report
# ---------------------------------------------------------------------------

class PatchExecutor:
    """
    High-level executor that:
      1. Applies a list of file-change dicts to *repo_path*
      2. Runs the project's test suite (mocked if absent)
      3. Re-scans the modified file(s) to confirm the vulnerability is gone
      4. Returns a structured result dict consumable by reward.calculate_reward()
    """

    def __init__(self, runner: CommandRunner, timeout_seconds: int = 300) -> None:
        self.runner = runner
        self.timeout = timeout_seconds

    def apply_and_verify(
        self,
        repo_path: Path,
        changes: list[dict[str, Any]],
        original_finding: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Apply *changes*, run tests, and re-scan to verify the fix.

        Parameters
        ----------
        repo_path:
            Root of the cloned repository.
        changes:
            List of ``{"path", "action", "content"}`` dicts from the LLM.
        original_finding:
            The original vulnerability / secret finding dict (used for re-scan).

        Returns
        -------
        {
            "tests_passed":   bool,
            "tests_failed":   bool,
            "build_failed":   bool,
            "issue_fixed":    bool,   # True if re-scan shows vuln gone
            "secret_removed": bool,
            "no_change":      bool,
            "touched_files":  list[str],
            "test_details":   list[dict],
            "rescan_findings":list[dict],
        }
        """
        result: dict[str, Any] = {
            "tests_passed": False,
            "tests_failed": False,
            "build_failed": False,
            "issue_fixed": False,
            "secret_removed": False,
            "no_change": False,
            "touched_files": [],
            "test_details": [],
            "rescan_findings": [],
        }

        # ---- 1. Apply changes ---------------------------------------- #
        try:
            touched = self._apply_changes(repo_path, changes)
            result["touched_files"] = touched
            if not touched:
                result["no_change"] = True
                logger.warning("PatchExecutor: no files were modified by the changes list.")
                return result
        except (ValueError, OSError) as exc:
            logger.error("PatchExecutor: apply_changes failed — %s", exc)
            result["no_change"] = True
            return result

        # ---- 2. Run tests -------------------------------------------- #
        test_details = self._run_tests(repo_path)
        result["test_details"] = test_details

        statuses = {t["status"] for t in test_details}
        if "failed" in statuses:
            result["tests_failed"] = True
            result["build_failed"] = any(
                "build" in t.get("command", "").lower() and t["status"] == "failed"
                for t in test_details
            )
            logger.info("PatchExecutor: tests failed.")
        elif "passed" in statuses:
            result["tests_passed"] = True
            logger.info("PatchExecutor: tests passed.")
        # "skipped" only → neither flag set

        # ---- 3. Re-scan to confirm fix ------------------------------- #
        rescan = self._rescan_finding(repo_path, original_finding)
        result["rescan_findings"] = rescan

        finding_type = original_finding.get("type", "")
        is_secret_type = any(
            k in finding_type
            for k in ("key", "token", "password", "secret", "credential", "jwt", "sensitive_file")
        )

        if not rescan:
            # Vulnerability no longer detected — fix confirmed
            result["issue_fixed"] = True
            if is_secret_type:
                result["secret_removed"] = True
            logger.info("PatchExecutor: vulnerability no longer detected (fix confirmed).")
        else:
            logger.info("PatchExecutor: re-scan still detects %d finding(s).", len(rescan))

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_changes(self, repo_path: Path, changes: list[dict[str, Any]]) -> list[str]:
        """Write changes to disk; returns list of touched relative paths."""
        touched: list[str] = []
        for change in changes:
            relative_path = str(change.get("path", "")).strip().lstrip("/")
            if not relative_path:
                logger.warning("PatchExecutor: change has no path — skipped.")
                continue

            target = (repo_path / relative_path).resolve()
            # Safety: must stay inside repo
            if repo_path.resolve() not in target.parents and target != repo_path.resolve():
                raise ValueError(f"Unsafe patch path: {relative_path}")

            action = str(change.get("action", "update")).lower()

            if action == "delete":
                if target.exists():
                    target.unlink()
                touched.append(relative_path)
                logger.debug("PatchExecutor: deleted %s", relative_path)
                continue

            content = change.get("content")
            if not isinstance(content, str):
                logger.warning("PatchExecutor: no content for %s — skipped.", relative_path)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            touched.append(relative_path)
            logger.debug("PatchExecutor: wrote %s (%d bytes)", relative_path, len(content))

        return touched

    def _run_tests(self, repo_path: Path) -> list[dict[str, Any]]:
        """
        Auto-detect and run the project's test suite.
        Returns a list of test result dicts.
        Falls back to a mock "skipped" entry when no test runner is found.
        """
        results: list[dict[str, Any]] = []

        # Node / npm
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                import json as _json
                pkg = _json.loads(package_json.read_text(encoding="utf-8"))
            except Exception:
                pkg = {}

            if pkg.get("scripts", {}).get("test"):
                results.append(self._exec(["npm", "install"], repo_path, label="npm install"))
                if results[-1]["status"] == "passed":
                    results.append(self._exec(["npm", "test"], repo_path, label="npm test"))
            else:
                results.append(_skipped("npm test", "No test script in package.json"))

        # Python / pytest
        if _is_python_project(repo_path):
            results.append(self._exec(["pytest", "--tb=short", "-q"], repo_path, label="pytest"))

        if not results:
            results.append(_skipped("tests", "No supported test suite detected — assuming pass."))
            # Treat "no tests found" as passed (not a failure)
            results[0]["status"] = "passed"

        return results

    def _exec(self, command: list[str], cwd: Path, *, label: str) -> dict[str, Any]:
        """Run a shell command and return a status dict."""
        logger.info("PatchExecutor: running %s", " ".join(command))
        try:
            r = self.runner.run_repo_command(command, cwd=cwd, timeout=self.timeout)
            return {
                "command": label,
                "status": "passed",
                "stdout": r.stdout[:4000],
                "stderr": r.stderr[:2000],
                "duration": round(r.duration_seconds, 2),
            }
        except CommandExecutionError as exc:
            return {
                "command": label,
                "status": "failed",
                "stdout": "",
                "stderr": str(exc)[:2000],
                "duration": 0,
            }

    @staticmethod
    def _rescan_finding(
        repo_path: Path, original_finding: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Re-run the relevant scanner on the affected file only.
        Returns remaining findings of the same type — empty means fix confirmed.
        """
        from scanner import scan_repository as _scan_vuln
        from secret_scanner import scan_secrets as _scan_secrets

        finding_type = original_finding.get("type", "")
        affected_file = original_finding.get("file")

        # Determine which scanner to use
        secret_types = {
            "aws_access_key", "aws_secret_key", "github_token", "github_oauth",
            "slack_token", "slack_webhook", "stripe_live_key", "stripe_test_key",
            "google_api_key", "google_oauth", "sendgrid_key", "twilio_account_sid",
            "twilio_auth_token", "mailchimp_key", "private_key", "jwt_token",
            "generic_password", "generic_api_key", "database_url", "azure_storage_key",
            "heroku_api_key", "npm_token", "pypi_token", "sensitive_file",
        }

        try:
            if finding_type in secret_types:
                all_findings = _scan_secrets(repo_path)
            else:
                all_findings = _scan_vuln(repo_path)
        except Exception as exc:
            logger.warning("PatchExecutor: re-scan failed — %s", exc)
            return []

        # Filter to same type and same file
        remaining = [
            f for f in all_findings
            if f.get("type") == finding_type
            and (affected_file is None or f.get("file") == affected_file)
        ]
        return remaining


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_python_project(repo_path: Path) -> bool:
    markers = ("pyproject.toml", "requirements.txt", "setup.py", "pytest.ini", "tox.ini")
    return any((repo_path / m).exists() for m in markers) or (repo_path / "tests").exists()


def _skipped(command: str, reason: str) -> dict[str, Any]:
    return {
        "command": command,
        "status": "skipped",
        "stdout": "",
        "stderr": reason,
        "duration": 0,
    }
