from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(slots=True)
class Settings:
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    hf_api_key: str = os.getenv("HF_API_KEY", "")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    frontend_origin_regex: str = os.getenv(
        "FRONTEND_ORIGIN_REGEX",
        r"https://.*\.vercel\.app",
    )
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    command_timeout_seconds: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "300"))
    git_author_name: str = os.getenv("GIT_AUTHOR_NAME", "OpenDev AI")
    git_author_email: str = os.getenv(
        "GIT_AUTHOR_EMAIL",
        "opendev-ai@users.noreply.github.com",
    )

    @property
    def missing_github(self) -> list[str]:
        return [name for name, value in {"GITHUB_TOKEN": self.github_token}.items() if not value]

    @property
    def has_llm_provider(self) -> bool:
        return bool(self.gemini_api_key or self.groq_api_key)

    @property
    def frontend_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]
        return origins or ["http://localhost:3000"]


settings = Settings()
