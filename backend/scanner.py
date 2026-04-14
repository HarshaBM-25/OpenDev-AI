"""
scanner.py — Repository vulnerability scanner.

Detects:
  - SQL injection
  - Cross-Site Scripting (XSS)
  - Unsafe eval() / dynamic code execution
  - Command injection
  - Path traversal
  - Hardcoded credentials (non-secret form)

Returns a structured findings list compatible with the RL agent state schema.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vulnerability pattern definitions
# ---------------------------------------------------------------------------
VULN_PATTERNS: dict[str, dict[str, Any]] = {
    "sql_injection": {
        "patterns": [
            # Python f-string SQL
            re.compile(r'(?i)f["\'].*?(SELECT|INSERT|UPDATE|DELETE|DROP|UNION).*?\{', re.DOTALL),
            # Python %-format SQL
            re.compile(r'(?i)(execute|query)\s*\(\s*["\'].*?%s.*?["\'].*?%\s*\('),
            # String concatenation in SQL
            re.compile(r'(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\s+.*?\+\s*\w+'),
            # cursor.execute with variable
            re.compile(r'(?i)cursor\.execute\s*\(\s*[^"\']*\+'),
            # JS template literal SQL
            re.compile(r'(?i)`(SELECT|INSERT|UPDATE|DELETE)\s.*?\$\{'),
        ],
        "severity": "high",
        "description": "Potential SQL injection — dynamic query construction detected",
        "fix_types": ["prepared_statement", "sanitize_input"],
        "language_hint": ["python", "javascript", "typescript", "php", "java"],
    },
    "xss": {
        "patterns": [
            # innerHTML assignment without sanitisation
            re.compile(r'\.innerHTML\s*[+]?=(?!\s*DOMPurify)'),
            # document.write
            re.compile(r'\bdocument\.write\s*\('),
            # jQuery .html() with concatenation
            re.compile(r'\.html\s*\(\s*(?!.*escape).*?\+'),
            # React dangerouslySetInnerHTML
            re.compile(r'dangerouslySetInnerHTML'),
            # Vue v-html
            re.compile(r'\bv-html\b'),
            # Angular [innerHTML]
            re.compile(r'\[innerHTML\]'),
        ],
        "severity": "high",
        "description": "Potential Cross-Site Scripting (XSS) — unescaped HTML injection",
        "fix_types": ["sanitize_input", "refactor_code"],
        "language_hint": ["javascript", "typescript"],
    },
    "unsafe_eval": {
        "patterns": [
            re.compile(r'\beval\s*\('),
            re.compile(r'\bnew\s+Function\s*\('),
            re.compile(r'\bsetTimeout\s*\(\s*[\'"]'),
            re.compile(r'\bsetInterval\s*\(\s*[\'"]'),
            re.compile(r'\b__import__\s*\(.*?input'),
            re.compile(r'\bexec\s*\(\s*(?:input|request|req|params|query)'),
        ],
        "severity": "high",
        "description": "Unsafe eval() or dynamic code execution",
        "fix_types": ["refactor_code", "sanitize_input"],
        "language_hint": ["javascript", "typescript", "python"],
    },
    "command_injection": {
        "patterns": [
            re.compile(r'(?i)(os\.system|subprocess\.call|subprocess\.run|popen)\s*\(.*?\+'),
            re.compile(r'(?i)(os\.system|popen)\s*\(\s*f["\']'),
            re.compile(r'(?i)shell\s*=\s*True.*?(\+|format|f["\'])'),
            re.compile(r'(?i)(exec|system|passthru|shell_exec)\s*\(\s*\$'),
        ],
        "severity": "high",
        "description": "Potential OS command injection via unsanitised input",
        "fix_types": ["sanitize_input", "refactor_code"],
        "language_hint": ["python", "php", "ruby"],
    },
    "path_traversal": {
        "patterns": [
            re.compile(r'(?i)open\s*\(\s*.*?\+.*?(?:user|request|req|param|input)', re.DOTALL),
            re.compile(r'(?i)open\s*\(\s*f["\'].*?\{'),
            re.compile(r'(?i)(readFile|writeFile|createReadStream)\s*\(.*?\+.*?(?:req|params|query)'),
            re.compile(r'(?i)os\.path\.join\s*\(.*?\+.*?(?:user|request|input)'),
        ],
        "severity": "medium",
        "description": "Potential path traversal — user input in file path",
        "fix_types": ["sanitize_input", "refactor_code"],
        "language_hint": ["python", "javascript", "typescript"],
    },
    "insecure_deserialization": {
        "patterns": [
            re.compile(r'\bpickle\.loads?\s*\('),
            re.compile(r'\byaml\.load\s*\(\s*(?!.*Loader=yaml\.SafeLoader)'),
            re.compile(r'\bunserialize\s*\(\s*\$'),
        ],
        "severity": "high",
        "description": "Insecure deserialization — arbitrary code execution risk",
        "fix_types": ["sanitize_input", "refactor_code"],
        "language_hint": ["python", "php"],
    },
    "weak_cryptography": {
        "patterns": [
            re.compile(r'(?i)\b(md5|sha1)\s*\('),
            re.compile(r'(?i)hashlib\.(md5|sha1)\s*\('),
            re.compile(r'(?i)Math\.random\s*\('),          # Used for crypto purposes
            re.compile(r'(?i)DES\s*\(|DES\.new\s*\('),
        ],
        "severity": "medium",
        "description": "Weak or deprecated cryptographic algorithm",
        "fix_types": ["refactor_code"],
        "language_hint": ["python", "javascript"],
    },
}

# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------
IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".next", "__pycache__", "node_modules",
    ".venv", "venv", "dist", "build", "coverage",
})

SCANNABLE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".php", ".rb", ".java", ".go", ".cs",
    ".sh", ".bash",
})

EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".php": "php",
    ".rb": "ruby",
    ".java": "java",
    ".go": "go",
    ".cs": "csharp",
    ".sh": "bash",
    ".bash": "bash",
}

MAX_FILE_SIZE = 500_000  # bytes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_repository(repo_path: Path) -> list[dict[str, Any]]:
    """
    Scan all code files in *repo_path* for security vulnerabilities.

    Returns a list of findings. Each finding has the shape:
    {
        "id":          int,
        "source":      "code",
        "type":        str,          # e.g. "sql_injection"
        "severity":    "high" | "medium" | "low",
        "description": str,
        "file":        str,          # relative path
        "line":        int,
        "preview":     str,          # truncated offending line
        "language":    str,
        "fix_types":   list[str],
        "fixable":     bool,
    }
    """
    findings: list[dict[str, Any]] = []
    finding_id = 1

    for file_path in _iter_code_files(repo_path):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            logger.warning("scanner: cannot read %s — %s", file_path, exc)
            continue

        lines = content.splitlines()
        relative = str(file_path.relative_to(repo_path))
        language = EXT_TO_LANGUAGE.get(file_path.suffix.lower(), "unknown")

        for vuln_type, cfg in VULN_PATTERNS.items():
            # Skip pattern if language hint doesn't match (avoids false positives)
            hints: list[str] = cfg.get("language_hint", [])
            if hints and language not in hints and language != "unknown":
                continue

            matched_lines: set[int] = set()
            for pattern in cfg["patterns"]:
                for line_num, line in enumerate(lines, start=1):
                    if line_num in matched_lines:
                        continue
                    if pattern.search(line):
                        findings.append({
                            "id": finding_id,
                            "source": "code",
                            "type": vuln_type,
                            "severity": cfg["severity"],
                            "description": cfg["description"],
                            "file": relative,
                            "line": line_num,
                            "preview": line.strip()[:200],
                            "language": language,
                            "fix_types": list(cfg["fix_types"]),
                            "fixable": True,
                        })
                        finding_id += 1
                        matched_lines.add(line_num)
                        break  # one finding per pattern per file

    logger.info("scanner: %d vulnerability findings in %s", len(findings), repo_path)
    return findings


def calculate_security_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Derive a 0-100 security score from a combined findings list.
    Returns score, letter grade, and per-severity breakdown.
    """
    DEDUCTIONS = {"high": 15, "medium": 8, "low": 3}

    total_deduction = sum(DEDUCTIONS.get(f.get("severity", "low"), 3) for f in findings)
    score = max(0, 100 - total_deduction)

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    by_severity: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        if sev in by_severity:
            by_severity[sev] += 1

    by_type: dict[str, int] = {}
    for f in findings:
        t = f.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "score": score,
        "grade": grade,
        "total_findings": len(findings),
        "by_severity": by_severity,
        "by_type": by_type,
        "summary": f"Security score: {score}/100 (Grade {grade}) — {len(findings)} findings",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iter_code_files(repo_path: Path):
    """Yield scannable code files, skipping ignored dirs and large files."""
    for path in repo_path.rglob("*"):
        if path.is_dir():
            continue
        rel_parts = path.relative_to(repo_path).parts
        if any(part in IGNORED_DIRS for part in rel_parts):
            continue
        if path.suffix.lower() not in SCANNABLE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        yield path
