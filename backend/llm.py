"""
llm.py — LLM service for OpenDev AI.

Supports:
  - generate_code(prompt)  → LLMResult   [original, unchanged]
  - generate_fix(issue, action, prompt)  → LLMResult  [new]

Providers (tried in priority order):
  1. Google Gemini
  2. Groq
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions & result types
# ---------------------------------------------------------------------------

class LLMError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMResult:
    provider: str
    parsed: dict[str, Any]
    raw: str = ""
    confidence: float = 1.0   # propagated from RL when set externally


# ---------------------------------------------------------------------------
# LLMService
# ---------------------------------------------------------------------------

class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    # Public: original API (unchanged)
    # ------------------------------------------------------------------

    def generate_code(self, prompt: str) -> LLMResult:
        """
        Generate code / a fix using the configured LLM providers.
        Tries Gemini first, then Groq as fallback.
        Returns an LLMResult with *parsed* being a dict.
        """
        return self._call_with_fallback(prompt)

    # ------------------------------------------------------------------
    # Public: new action-aware fix generation
    # ------------------------------------------------------------------

    def generate_fix(
        self,
        issue: dict[str, Any],
        action: str,
        prompt: str | None = None,
    ) -> LLMResult:
        """
        Generate a production-ready fix for *issue* using *action* as guidance.

        Parameters
        ----------
        issue:
            A finding dict (from scanner, secret_scanner, or issue_analyzer).
        action:
            The RL-chosen fix strategy (e.g. "prepared_statement").
        prompt:
            Optional pre-built prompt. If None, a default is generated.

        Returns
        -------
        LLMResult with *parsed* containing at minimum a "changes" list.
        """
        if prompt is None:
            prompt = self._build_fix_prompt(issue, action)

        result = self._call_with_fallback(prompt)

        # Guarantee "changes" key exists even if LLM omits it
        if "changes" not in result.parsed:
            result.parsed["changes"] = []

        logger.info(
            "generate_fix: provider=%s action=%s type=%s changes=%d",
            result.provider, action,
            issue.get("type", "unknown"),
            len(result.parsed.get("changes", [])),
        )
        return result

    def generate_issue_summary(self, issue: dict[str, Any]) -> str:
        """
        Quick LLM call to produce a one-sentence summary of a GitHub issue.
        Returns the summary string (falls back to the issue title on error).
        """
        prompt = (
            "Summarise the following GitHub issue in one sentence. "
            "Return plain text — no JSON, no markdown.\n\n"
            f"Title: {issue.get('title', '')}\n"
            f"Body:\n{(issue.get('body') or '')[:800]}\n"
        )
        try:
            if self.settings.gemini_api_key:
                return self._call_gemini_text(prompt)
            if self.settings.groq_api_key:
                return self._call_groq_text(prompt)
        except Exception as exc:
            logger.warning("generate_issue_summary failed: %s", exc)
        return issue.get("title", "No summary available.")

    # ------------------------------------------------------------------
    # Internal: provider calls
    # ------------------------------------------------------------------

    def _call_with_fallback(self, prompt: str) -> LLMResult:
        """Try Gemini → Groq and return the first successful result."""
        errors: list[str] = []

        if self.settings.gemini_api_key:
            try:
                raw = self._call_gemini(prompt)
                return LLMResult(provider="gemini", parsed=self._parse_json(raw), raw=raw)
            except Exception as exc:
                errors.append(f"Gemini: {exc}")
                logger.warning("llm: Gemini failed — %s", exc)

        if self.settings.groq_api_key:
            try:
                raw = self._call_groq(prompt)
                return LLMResult(provider="groq", parsed=self._parse_json(raw), raw=raw)
            except Exception as exc:
                errors.append(f"Groq: {exc}")
                logger.warning("llm: Groq failed — %s", exc)

        raise LLMError("; ".join(errors) or "No LLM provider is configured.")

    def _call_gemini(self, prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent?key={self.settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise LLMError("Gemini returned an empty response.")
        return text

    def _call_gemini_text(self, prompt: str) -> str:
        """Gemini call for plain-text (non-JSON) responses."""
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent?key={self.settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts).strip()

    def _call_groq(self, prompt: str) -> str:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.groq_model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return valid JSON only. Do not wrap in markdown backticks.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("Groq returned no choices.")
        text = choices[0].get("message", {}).get("content", "").strip()
        if not text:
            raise LLMError("Groq returned an empty response.")
        return text

    def _call_groq_text(self, prompt: str) -> str:
        """Groq call for plain-text responses."""
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.groq_model,
                "temperature": 0.2,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            raise LLMError("Groq returned no choices.")
        return choices[0].get("message", {}).get("content", "").strip()

    # ------------------------------------------------------------------
    # Internal: prompt builder for action-aware fixes
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fix_prompt(issue: dict[str, Any], action: str) -> str:
        from rules import get_action_description  # avoid circular at import time
        action_desc = get_action_description(action)
        is_issue = issue.get("source") == "issue"

        if is_issue:
            context = (
                f"GitHub Issue #{issue.get('issue_number', '?')}: {issue.get('title', '')}\n"
                f"Type: {issue.get('type')} | Severity: {issue.get('severity')}\n"
                f"Summary: {issue.get('summary', '')}\n"
                f"Body:\n{(issue.get('body') or '')[:1000]}\n"
            )
        else:
            context = (
                f"Security Finding — {issue.get('type')}\n"
                f"Severity: {issue.get('severity')} | File: {issue.get('file', 'N/A')} "
                f"(line {issue.get('line', 'N/A')})\n"
                f"Description: {issue.get('description', '')}\n"
                f"Preview: {issue.get('preview', '')}\n"
            )

        return (
            "You are OpenDev AI, an autonomous security and code-quality remediation agent.\n"
            "Generate a minimal, production-safe fix using the strategy specified below.\n"
            "Return JSON ONLY — no markdown, no explanation outside the JSON.\n\n"
            "Required JSON shape:\n"
            "{\n"
            '  "summary":        "one-sentence fix description",\n'
            '  "commit_message": "conventional commit message",\n'
            '  "pr_title":       "pull request title",\n'
            '  "pr_body":        "pull request markdown body",\n'
            '  "confidence":     0.0-1.0,\n'
            '  "changes": [\n'
            '    {\n'
            '      "path":    "relative/file/path",\n'
            '      "action":  "update | create | delete",\n'
            '      "content": "complete new file content (required for update/create)"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "CONSTRAINTS:\n"
            "- Fix ONLY the described issue; leave all other code unchanged.\n"
            "- Match the file's existing coding style and indentation exactly.\n"
            "- If you cannot generate a safe fix, return an empty 'changes' list.\n"
            "- Never introduce new external dependencies.\n\n"
            f"Fix strategy: {action}\n"
            f"Strategy guidance: {action_desc}\n\n"
            f"Finding:\n{context}"
        )

    # ------------------------------------------------------------------
    # Internal: JSON parsing (unchanged from original)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise LLMError("Model response was not valid JSON.")
            return json.loads(match.group(0))
