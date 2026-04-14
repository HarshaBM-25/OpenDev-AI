"""
rules.py — Declarative mapping of vulnerability/issue types to fix strategies.

Used by the RL agent to determine the candidate action space for each finding.
Also provides rich context strings that the LLM uses when generating a fix.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# All possible fix actions (action space)
# ---------------------------------------------------------------------------
ALL_ACTIONS: list[str] = [
    "sanitize_input",       # Validate/escape/allowlist user-supplied values
    "prepared_statement",   # Parameterised queries / ORM instead of raw SQL
    "move_to_env",          # Move secrets to environment variables
    "refactor_code",        # General-purpose structural or logic refactor
    "fix_issue_logic",      # Fix the specific business-logic defect
]

# ---------------------------------------------------------------------------
# Core rules table: issue/vuln type → ordered list of applicable actions
# (earlier entries = typically more appropriate for this type)
# ---------------------------------------------------------------------------
RULES: dict[str, list[str]] = {
    # ---- Code vulnerabilities (from scanner.py) --------------------------
    "sql_injection":              ["prepared_statement", "sanitize_input", "refactor_code"],
    "xss":                        ["sanitize_input", "refactor_code"],
    "unsafe_eval":                ["refactor_code", "sanitize_input"],
    "command_injection":          ["sanitize_input", "refactor_code"],
    "path_traversal":             ["sanitize_input", "refactor_code"],
    "insecure_deserialization":   ["refactor_code", "sanitize_input"],
    "weak_cryptography":          ["refactor_code"],
    "hardcoded_credentials":      ["move_to_env", "refactor_code"],

    # ---- Secrets (from secret_scanner.py) --------------------------------
    "aws_access_key":             ["move_to_env"],
    "aws_secret_key":             ["move_to_env"],
    "github_token":               ["move_to_env"],
    "github_oauth":               ["move_to_env"],
    "slack_token":                ["move_to_env"],
    "slack_webhook":              ["move_to_env"],
    "stripe_live_key":            ["move_to_env"],
    "stripe_test_key":            ["move_to_env"],
    "google_api_key":             ["move_to_env"],
    "google_oauth":               ["move_to_env"],
    "sendgrid_key":               ["move_to_env"],
    "twilio_account_sid":         ["move_to_env"],
    "twilio_auth_token":          ["move_to_env"],
    "mailchimp_key":              ["move_to_env"],
    "private_key":                ["move_to_env", "refactor_code"],
    "jwt_token":                  ["move_to_env", "refactor_code"],
    "generic_password":           ["move_to_env", "sanitize_input"],
    "generic_api_key":            ["move_to_env"],
    "database_url":               ["move_to_env"],
    "azure_storage_key":          ["move_to_env"],
    "heroku_api_key":             ["move_to_env"],
    "npm_token":                  ["move_to_env"],
    "pypi_token":                 ["move_to_env"],
    "sensitive_file":             ["move_to_env", "refactor_code"],

    # ---- GitHub issue types (from issue_analyzer.py) --------------------
    "bug":                        ["fix_issue_logic", "refactor_code", "sanitize_input"],
    "security":                   ["sanitize_input", "move_to_env", "prepared_statement", "refactor_code"],
    "performance":                ["refactor_code", "fix_issue_logic"],
    "feature":                    ["fix_issue_logic", "refactor_code"],
    "documentation":              ["refactor_code"],
    "dependency":                 ["refactor_code", "fix_issue_logic"],
    "configuration":              ["move_to_env", "refactor_code"],
    "test":                       ["fix_issue_logic", "refactor_code"],
    "style":                      ["refactor_code"],
    "unknown":                    ["fix_issue_logic", "refactor_code"],

    # ---- Legacy types from original agent.py scan -----------------------
    "env_file":                   ["move_to_env"],
    "node_modules":               ["refactor_code"],
    "generic_secret":             ["move_to_env"],
    "aws_access_key_vuln":        ["move_to_env"],
    "private_key_header":         ["move_to_env", "refactor_code"],
}

# ---------------------------------------------------------------------------
# Human-readable descriptions for each action (used in LLM prompts)
# ---------------------------------------------------------------------------
ACTION_DESCRIPTIONS: dict[str, str] = {
    "sanitize_input": (
        "Sanitise and validate all user-supplied inputs. "
        "Apply allowlists, type checks, and context-aware escaping (e.g. HTML encode for web, "
        "shell-quote for commands)."
    ),
    "prepared_statement": (
        "Replace dynamic SQL string construction with parameterised queries or ORM methods. "
        "Never interpolate user data directly into SQL strings."
    ),
    "move_to_env": (
        "Remove the hardcoded secret from source code and load it at runtime from an environment variable. "
        "Add the file / variable name to .gitignore and provide a .env.example template."
    ),
    "refactor_code": (
        "Refactor the affected code to eliminate the vulnerability or logic error. "
        "Use safe library alternatives, reduce complexity, and follow the principle of least privilege."
    ),
    "fix_issue_logic": (
        "Identify and correct the business-logic defect described in the issue. "
        "Add or update tests that demonstrate the fix."
    ),
}

# ---------------------------------------------------------------------------
# Severity → priority weight (used externally when sorting/batching)
# ---------------------------------------------------------------------------
SEVERITY_WEIGHT: dict[str, int] = {"high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_actions(issue_type: str) -> list[str]:
    """
    Return the ordered list of applicable fix actions for *issue_type*.
    Falls back to generic actions when the type is not in RULES.
    """
    return list(RULES.get(issue_type, ["fix_issue_logic", "refactor_code"]))


def get_action_description(action: str) -> str:
    """Return the LLM-prompt description for *action*."""
    return ACTION_DESCRIPTIONS.get(action, action)


def build_action_context(action: str, issue: dict[str, Any]) -> str:
    """
    Compose a context string that is injected into the LLM fix-generation prompt.
    Tells the model *what* to do and *why*.
    """
    desc = get_action_description(action)
    issue_type = issue.get("type", "unknown")
    severity = issue.get("severity", "medium")
    file_info = f" in `{issue['file']}`" if issue.get("file") else ""
    line_info = f" (line {issue['line']})" if issue.get("line") else ""

    return (
        f"**Selected fix strategy:** `{action}`\n"
        f"**Guidance:** {desc}\n"
        f"**Issue type:** {issue_type} | **Severity:** {severity}{file_info}{line_info}"
    )


def get_all_actions() -> list[str]:
    """Return the full action space."""
    return list(ALL_ACTIONS)


def sort_findings_by_priority(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort findings from most to least severe, then by type for determinism."""
    return sorted(
        findings,
        key=lambda f: (
            -SEVERITY_WEIGHT.get(f.get("severity", "low"), 0),
            f.get("type", ""),
        ),
    )
