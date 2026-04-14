"""
issue_analyzer.py — GitHub issue fetcher and LLM-powered classifier.

Responsibilities:
  1. Fetch open GitHub issues via github_service.GitHubService
  2. Use the LLM to summarise and classify each issue
  3. Map every issue to a concrete fix-type list
  4. Return a structured list compatible with the RL agent state schema
"""
from __future__ import annotations

import logging
from typing import Any

from github_service import GitHubService
from llm import LLMService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping: issue type → applicable fix strategies
# ---------------------------------------------------------------------------
ISSUE_TYPE_FIX_MAP: dict[str, list[str]] = {
    "bug":           ["fix_issue_logic", "refactor_code", "sanitize_input"],
    "security":      ["sanitize_input", "move_to_env", "prepared_statement", "refactor_code"],
    "performance":   ["refactor_code", "fix_issue_logic"],
    "feature":       ["fix_issue_logic", "refactor_code"],
    "documentation": ["refactor_code"],
    "dependency":    ["refactor_code", "fix_issue_logic"],
    "configuration": ["move_to_env", "refactor_code"],
    "test":          ["fix_issue_logic", "refactor_code"],
    "style":         ["refactor_code"],
    "unknown":       ["fix_issue_logic", "refactor_code"],
}

VALID_TYPES: frozenset[str] = frozenset(ISSUE_TYPE_FIX_MAP)

# Labels that strongly indicate type / severity
_LABEL_TYPE_MAP: dict[str, str] = {
    "bug": "bug", "crash": "bug", "defect": "bug",
    "security": "security", "vulnerability": "security", "cve": "security",
    "performance": "performance", "slow": "performance", "memory-leak": "performance",
    "enhancement": "feature", "feature": "feature", "feature-request": "feature",
    "documentation": "documentation", "docs": "documentation",
    "dependencies": "dependency", "dependency": "dependency",
    "configuration": "configuration",
    "test": "test", "testing": "test",
    "style": "style", "formatting": "style",
}

_KEYWORD_TYPE_MAP: dict[str, str] = {
    "sql": "security", "injection": "security", "xss": "security",
    "csrf": "security", "auth": "security", "vulnerability": "security",
    "exploit": "security", "overflow": "security",
    "error": "bug", "exception": "bug", "crash": "bug",
    "fail": "bug", "broken": "bug", "wrong": "bug", "incorrect": "bug",
    "slow": "performance", "timeout": "performance", "memory": "performance",
    "cpu": "performance", "optimize": "performance", "perf": "performance",
    "feature": "feature", "add": "feature", "implement": "feature",
    "support": "feature", "request": "feature",
    "doc": "documentation", "readme": "documentation", "typo": "documentation",
    "dependency": "dependency", "package": "dependency", "upgrade": "dependency",
    "env": "configuration", "config": "configuration", "setting": "configuration",
    "test": "test", "coverage": "test", "spec": "test",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_issues(
    github_service: GitHubService,
    llm_service: LLMService,
    repo_url: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Fetch open GitHub issues for *repo_url* and classify each with the LLM.

    Returns a list of analysed-issue dicts:
    {
        "source":       "issue",
        "type":         str,          # bug / security / …
        "severity":     str,          # high / medium / low
        "issue_number": int,
        "title":        str,
        "body":         str,
        "url":          str,
        "labels":       list[str],
        "summary":      str,          # LLM one-sentence summary
        "fix_types":    list[str],    # applicable fix strategies
        "language":     "unknown",    # inferred later from repo context
        "confidence":   float,        # 0–1 classification confidence
        "fixable":      bool,
    }
    """
    try:
        raw_issues = github_service.get_open_issues(repo_url, limit=limit)
    except Exception as exc:
        logger.error("issue_analyzer: failed to fetch issues — %s", exc)
        return []

    analyzed: list[dict[str, Any]] = []

    for issue in raw_issues:
        try:
            classification = _classify_with_llm(llm_service, issue)
        except Exception as exc:
            logger.warning(
                "issue_analyzer: LLM classification failed for #%s — %s; using fallback",
                issue["number"], exc,
            )
            classification = _fallback_classify(issue)

        issue_type = classification.get("type", "unknown")
        severity = classification.get("severity", "medium")
        summary = classification.get("summary") or issue["title"]
        confidence = float(classification.get("confidence", 0.5))
        fix_types = ISSUE_TYPE_FIX_MAP.get(issue_type, ["fix_issue_logic"])

        analyzed.append({
            "source": "issue",
            "type": issue_type,
            "severity": severity,
            "issue_number": issue["number"],
            "title": issue["title"],
            "body": (issue.get("body") or "")[:2000],
            "url": issue.get("url", ""),
            "labels": issue.get("labels", []),
            "summary": summary,
            "fix_types": fix_types,
            "language": "unknown",
            "confidence": round(confidence, 3),
            "fixable": True,
        })
        logger.debug(
            "issue_analyzer: #%s → type=%s severity=%s conf=%.2f",
            issue["number"], issue_type, severity, confidence,
        )

    logger.info("issue_analyzer: classified %d issues from %s", len(analyzed), repo_url)
    return analyzed


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _classify_with_llm(llm_service: LLMService, issue: dict[str, Any]) -> dict[str, Any]:
    """Call the LLM to classify a single issue. Returns normalised classification dict."""
    body_excerpt = (issue.get("body") or "No description provided.")[:1200]
    labels_str = ", ".join(issue.get("labels", [])) or "none"

    prompt = (
        "You are a GitHub issue classifier. Classify the issue below and return JSON ONLY.\n"
        "Use this exact shape — no extra keys:\n"
        "{\n"
        '  "type":       "bug|security|performance|feature|documentation|dependency|configuration|test|style|unknown",\n'
        '  "severity":   "high|medium|low",\n'
        '  "summary":    "<one-sentence summary of what needs to be fixed>",\n'
        '  "confidence": <float 0.0–1.0>\n'
        "}\n\n"
        f"Issue #{issue['number']}: {issue['title']}\n"
        f"Labels: {labels_str}\n"
        f"Body:\n{body_excerpt}\n"
    )

    result = llm_service.generate_code(prompt)
    parsed = result.parsed

    # Normalise type
    raw_type = str(parsed.get("type", "unknown")).lower().strip()
    parsed["type"] = raw_type if raw_type in VALID_TYPES else "unknown"

    # Normalise severity
    raw_severity = str(parsed.get("severity", "medium")).lower().strip()
    parsed["severity"] = raw_severity if raw_severity in {"high", "medium", "low"} else "medium"

    # Clamp confidence
    try:
        parsed["confidence"] = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
    except (TypeError, ValueError):
        parsed["confidence"] = 0.5

    return parsed


def _fallback_classify(issue: dict[str, Any]) -> dict[str, Any]:
    """
    Keyword + label based classification used when the LLM is unavailable.
    Confidence is capped at 0.4 to reflect lower reliability.
    """
    text = " ".join([
        issue.get("title", ""),
        issue.get("body", ""),
        " ".join(issue.get("labels", [])),
    ]).lower()

    labels_lower = [lbl.lower() for lbl in issue.get("labels", [])]

    # 1. Try labels first (most reliable signal)
    issue_type = "unknown"
    for lbl in labels_lower:
        if lbl in _LABEL_TYPE_MAP:
            issue_type = _LABEL_TYPE_MAP[lbl]
            break

    # 2. Fall back to keyword matching
    if issue_type == "unknown":
        for keyword, t in _KEYWORD_TYPE_MAP.items():
            if keyword in text:
                issue_type = t
                break

    # Severity heuristics
    severity = "medium"
    if any(k in text for k in ("critical", "urgent", "security", "vulnerability", "high", "exploit")):
        severity = "high"
    elif any(k in text for k in ("minor", "low", "nice to have", "enhancement", "typo", "docs")):
        severity = "low"

    return {
        "type": issue_type,
        "severity": severity,
        "summary": issue.get("title", "No title"),
        "confidence": 0.35,
    }
