"""
pr_reviewer.py — AI-powered pull request reviewer.

Fetches PR diff, changed files, and comments, then uses LLM to:
  - Summarise what the PR does
  - Check for bugs, security issues, style problems
  - Give line-by-line suggestions
  - Recommend: MERGE / REQUEST_CHANGES / COMMENT
  - Post review comment back to GitHub (optional)
"""
from __future__ import annotations

import logging
from typing import Any

from github import Github, GithubException

logger = logging.getLogger(__name__)

# Max chars of diff sent to LLM (to stay within context window)
MAX_DIFF_CHARS = 12_000


def fetch_pr_details(token: str, repo_url: str, pr_number: int) -> dict[str, Any]:
    """
    Fetch all PR metadata, diff, and existing comments from GitHub.
    Returns a rich dict ready for analysis.
    """
    g = Github(token)
    slug = _extract_slug(repo_url)
    repo = g.get_repo(slug)

    try:
        pr = repo.get_pull(pr_number)
    except GithubException as exc:
        raise ValueError(f"PR #{pr_number} not found: {exc}") from exc

    # Changed files
    changed_files: list[dict[str, Any]] = []
    for f in pr.get_files():
        changed_files.append({
            "filename": f.filename,
            "status": f.status,          # added / modified / removed
            "additions": f.additions,
            "deletions": f.deletions,
            "patch": (f.patch or "")[:3000],
        })

    # Existing review comments
    reviews: list[dict[str, Any]] = []
    for review in pr.get_reviews():
        reviews.append({
            "author": review.user.login if review.user else "unknown",
            "state": review.state,
            "body": (review.body or "")[:500],
        })

    # Commits
    commits: list[str] = [c.commit.message.splitlines()[0] for c in pr.get_commits()]

    return {
        "number": pr.number,
        "title": pr.title,
        "body": (pr.body or "")[:1000],
        "author": pr.user.login if pr.user else "unknown",
        "state": pr.state,
        "merged": pr.merged,
        "mergeable": pr.mergeable,
        "base_branch": pr.base.ref,
        "head_branch": pr.head.ref,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": changed_files,
        "commits": commits,
        "existing_reviews": reviews,
        "url": pr.html_url,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "labels": [lbl.name for lbl in pr.labels],
    }


def build_review_prompt(pr_details: dict[str, Any]) -> str:
    """Build the LLM prompt for PR analysis."""
    files_section = "\n".join(
        f"### {f['filename']} ({f['status']}, +{f['additions']} -{f['deletions']})\n"
        f"```diff\n{f['patch'][:2000]}\n```"
        for f in pr_details["changed_files"][:10]
    )

    commits_str = "\n".join(f"- {c}" for c in pr_details["commits"][:10])
    existing_reviews_str = "\n".join(
        f"- {r['author']} ({r['state']}): {r['body'][:200]}"
        for r in pr_details["existing_reviews"][:5]
    ) or "None"

    return f"""You are an expert senior software engineer conducting a code review.
Analyse this pull request and return JSON ONLY — no markdown outside the JSON.

Required JSON shape:
{{
  "summary": "2-3 sentence summary of what this PR does",
  "recommendation": "MERGE | REQUEST_CHANGES | COMMENT",
  "confidence": 0.0-1.0,
  "overall_quality": "excellent | good | fair | poor",
  "issues": [
    {{
      "severity": "critical | major | minor | suggestion",
      "file": "filename or null",
      "line": null,
      "category": "bug | security | performance | style | logic | documentation",
      "description": "clear explanation of the issue",
      "suggestion": "concrete fix suggestion"
    }}
  ],
  "positives": ["list of things done well"],
  "review_comment": "The full review comment text to post on GitHub (Markdown format, professional tone)"
}}

RULES:
- Be specific, constructive, and professional
- MERGE only if code is correct and safe
- REQUEST_CHANGES if there are bugs, security issues, or major problems
- COMMENT for minor issues or suggestions only
- Check for: SQL injection, XSS, hardcoded secrets, missing error handling, N+1 queries, race conditions

PR #{pr_details['number']}: {pr_details['title']}
Author: {pr_details['author']}
Branch: {pr_details['head_branch']} → {pr_details['base_branch']}
Changes: +{pr_details['additions']} -{pr_details['deletions']} across {len(pr_details['changed_files'])} files

Description:
{pr_details['body'] or 'No description provided.'}

Commits:
{commits_str}

Existing reviews:
{existing_reviews_str}

Changed files:
{files_section}
"""


def post_review_comment(
    token: str,
    repo_url: str,
    pr_number: int,
    review_body: str,
    event: str = "COMMENT",  # MERGE | REQUEST_CHANGES | COMMENT | APPROVE
) -> dict[str, Any]:
    """Post a review comment to the PR on GitHub."""
    g = Github(token)
    repo = g.get_repo(_extract_slug(repo_url))
    pr = repo.get_pull(pr_number)

    # Map our recommendation to GitHub event type
    event_map = {
        "MERGE": "APPROVE",
        "REQUEST_CHANGES": "REQUEST_CHANGES",
        "COMMENT": "COMMENT",
        "APPROVE": "APPROVE",
    }
    gh_event = event_map.get(event.upper(), "COMMENT")

    try:
        review = pr.create_review(body=review_body, event=gh_event)
        return {
            "review_id": review.id,
            "state": review.state,
            "url": pr.html_url,
            "posted": True,
        }
    except GithubException as exc:
        logger.warning("post_review_comment: failed to post — %s", exc)
        return {"posted": False, "error": str(exc)}


def _extract_slug(repo_url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(repo_url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {repo_url}")
    return "/".join(parts[:2])
