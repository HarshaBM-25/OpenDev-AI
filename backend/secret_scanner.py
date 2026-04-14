"""
secret_scanner.py — Exposed secret and credential detector.
Skips .env.example, .env.sample, .env.template (safe files).
Detects: AWS/GCP/Azure, GitHub, Stripe, Firebase, MongoDB, Supabase,
         PostgreSQL, OpenAI, Anthropic, Discord, private keys, JWT, passwords.
"""
from __future__ import annotations
import fnmatch, logging, re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SECRET_PATTERNS: dict[str, dict[str, Any]] = {
    "aws_access_key":          {"pattern": re.compile(r"AKIA[0-9A-Z]{16}"),                                  "severity": "high",   "description": "AWS Access Key ID"},
    "github_token":            {"pattern": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),                         "severity": "high",   "description": "GitHub personal access token"},
    "slack_token":             {"pattern": re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),                      "severity": "high",   "description": "Slack API token"},
    "slack_webhook":           {"pattern": re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+"), "severity": "high", "description": "Slack Webhook URL"},
    "stripe_live_key":         {"pattern": re.compile(r"(?:sk|pk)_live_[0-9a-zA-Z]{24,}"),                    "severity": "high",   "description": "Stripe live API key"},
    "stripe_test_key":         {"pattern": re.compile(r"(?:sk|pk)_test_[0-9a-zA-Z]{24,}"),                    "severity": "medium", "description": "Stripe test API key"},
    "google_firebase_api_key": {"pattern": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),                             "severity": "high",   "description": "Google / Firebase API key"},
    "firebase_config":         {"pattern": re.compile(r'(?i)(?:firebaseConfig|initializeApp)\s*\(\s*\{[^}]*apiKey\s*:\s*["\'][^"\']{10,}["\']'), "severity": "high", "description": "Firebase client config with API key"},
    "firebase_service_account":{"pattern": re.compile(r'"type"\s*:\s*"service_account"'),                     "severity": "high",   "description": "Firebase service account credentials"},
    "mongodb_uri":             {"pattern": re.compile(r"mongodb(?:\+srv)?://[A-Za-z0-9_\-]+:[^@\s\"'<>]{4,}@[A-Za-z0-9\-\.]+"), "severity": "high", "description": "MongoDB connection string with credentials"},
    "supabase_service_key":    {"pattern": re.compile(r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "severity": "high", "description": "Supabase / JWT service key"},
    "postgres_url":            {"pattern": re.compile(r"postgres(?:ql)?://[A-Za-z0-9_\-]+:[^@\s\"'<>]{4,}@[A-Za-z0-9\-\.]+"), "severity": "high", "description": "PostgreSQL connection string with credentials"},
    "sendgrid_key":            {"pattern": re.compile(r"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}"),        "severity": "high",   "description": "SendGrid API key"},
    "twilio_account_sid":      {"pattern": re.compile(r"\bAC[a-z0-9]{32}\b"),                                 "severity": "medium", "description": "Twilio Account SID"},
    "private_key":             {"pattern": re.compile(r"-----BEGIN\s+(?:RSA|OPENSSH|EC|DSA|PGP)\s+PRIVATE\s+KEY"), "severity": "high", "description": "Private cryptographic key"},
    "openai_key":              {"pattern": re.compile(r"sk-[A-Za-z0-9]{48}"),                                  "severity": "high",   "description": "OpenAI API key"},
    "anthropic_key":           {"pattern": re.compile(r"sk-ant-[A-Za-z0-9\-_]{90,}"),                          "severity": "high",   "description": "Anthropic API key"},
    "discord_token":           {"pattern": re.compile(r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}"),            "severity": "high",   "description": "Discord bot token"},
    "npm_token":               {"pattern": re.compile(r"npm_[A-Za-z0-9]{36}"),                                 "severity": "high",   "description": "NPM access token"},
    "azure_storage":           {"pattern": re.compile(r"(?i)AccountKey=[A-Za-z0-9/+=]{88}"),                   "severity": "high",   "description": "Azure Storage account key"},
    "generic_password": {
        "pattern": re.compile(r'(?i)(?:password|passwd|pwd)\s*[=:]\s*[\'"](?!.*?(?:REDACTED|example|placeholder|changeme|your_|<|\*|dummy|test|fake|123|abc))[^\'"]{8,}[\'"]'),
        "severity": "high", "description": "Hardcoded password",
    },
    "generic_api_key": {
        "pattern": re.compile(r'(?i)(?:api[_\-]?key|apikey|api[_\-]?secret|client[_\-]?secret|access[_\-]?token)\s*[=:]\s*["\'](?!.*?(?:REDACTED|example|placeholder|your_|<|\*|dummy|test|undefined|null))[A-Za-z0-9_\-\/+=]{12,}["\']'),
        "severity": "high", "description": "Hardcoded API key / secret",
    },
}

SENSITIVE_FILE_PATTERNS: list[tuple[str, str, str]] = [
    ("*.pem",                    "high",   "PEM certificate/key file committed"),
    ("*.key",                    "high",   "Private key file committed"),
    ("*.pfx",                    "high",   "PKCS12 bundle committed"),
    ("*.jks",                    "high",   "Java KeyStore committed"),
    ("id_rsa",                   "high",   "SSH private key committed"),
    ("id_dsa",                   "high",   "SSH private key committed"),
    ("id_ed25519",               "high",   "SSH private key committed"),
    (".env",                     "high",   ".env file with credentials committed"),
    (".env.local",               "high",   ".env.local committed"),
    (".env.production",          "high",   ".env.production committed"),
    (".env.staging",             "high",   ".env.staging committed"),
    (".env.development",         "medium", ".env.development committed"),
    ("serviceAccountKey.json",   "high",   "Firebase service account committed"),
    ("service-account*.json",    "high",   "GCP service account committed"),
    ("google-services.json",     "high",   "Firebase google-services.json committed"),
    ("GoogleService-Info.plist", "high",   "Firebase iOS config committed"),
    ("credentials.json",         "high",   "Credentials file committed"),
    ("secrets.json",             "high",   "Secrets file committed"),
    (".netrc",                   "high",   ".netrc credentials committed"),
]

# Never flag these — they are safe templates
SAFE_FILES: frozenset[str] = frozenset({
    ".env.example", ".env.sample", ".env.template", ".env.test", ".env.ci", ".env.schema",
})

IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".next", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", "coverage",
})

SCANNABLE_EXTS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".sh", ".toml", ".cfg", ".ini", ".conf", ".rb", ".go", ".java",
    ".cs", ".php", ".tf", ".tfvars", ".xml", ".txt", ".md", ".env",
})


def scan_secrets(repo_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    fid = 1

    # Pass 1: sensitive files
    for fp in repo_path.rglob("*"):
        if fp.is_dir() or _ignored(fp, repo_path):
            continue
        if fp.name in SAFE_FILES:
            continue
        m = _match_file(fp.name)
        if m:
            sev, desc = m
            findings.append({"id": fid, "source": "code", "type": "sensitive_file",
                             "severity": sev, "description": desc,
                             "file": str(fp.relative_to(repo_path)), "line": None,
                             "preview": f"Sensitive file: {fp.name}",
                             "fix_types": ["move_to_env"], "fixable": True})
            fid += 1

    # Pass 2: content patterns
    seen: set[tuple[str, str, int]] = set()
    for fp in repo_path.rglob("*"):
        if fp.is_dir() or _ignored(fp, repo_path):
            continue
        if fp.name in SAFE_FILES:
            continue
        is_env = fp.name.startswith(".env")
        if not is_env and fp.suffix.lower() not in SCANNABLE_EXTS:
            continue
        try:
            if fp.stat().st_size > 500_000:
                continue
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel = str(fp.relative_to(repo_path))
        for stype, cfg in SECRET_PATTERNS.items():
            for lnum, line in enumerate(content.splitlines(), 1):
                key = (rel, stype, lnum)
                if key in seen:
                    continue
                match = cfg["pattern"].search(line)
                if match:
                    raw = match.group(0)
                    findings.append({"id": fid, "source": "code", "type": stype,
                                    "severity": cfg["severity"], "description": cfg["description"],
                                    "file": rel, "line": lnum,
                                    "preview": line.strip()[:200].replace(raw, _mask(raw)),
                                    "fix_types": ["move_to_env"], "fixable": True})
                    fid += 1
                    seen.add(key)
                    break

    logger.info("secret_scanner: %d findings", len(findings))
    return findings


def _ignored(fp: Path, root: Path) -> bool:
    try:
        return any(p in IGNORED_DIRS for p in fp.relative_to(root).parts)
    except ValueError:
        return True


def _match_file(name: str) -> tuple[str, str] | None:
    if name in SAFE_FILES:
        return None
    for pat, sev, desc in SENSITIVE_FILE_PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return sev, desc
    return None


def _mask(s: str) -> str:
    return f"{s[:4]}{'*' * min(len(s)-8, 10)}{s[-4:]}" if len(s) > 8 else "***"
