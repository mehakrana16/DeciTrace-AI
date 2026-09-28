"""Central configuration for DeciTrace AI.

Everything is driven by environment variables (see ``.env.example``).
No secret is ever hardcoded: when an LLM key is absent the application
starts in *deterministic template mode* and remains fully functional.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

# decitrace/backend/app/config.py -> ROOT == decitrace/
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return default if value is None or value == "" else value


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


class Settings:
    """Runtime settings, resolved once at import time."""

    APP_NAME: str = "DeciTrace AI"
    TAGLINE: str = "Evidence-Grounded Business Decision Engine"
    VERSION: str = "1.0.0"
    PROBLEM_STATEMENT: str = "PS-04 — AI Decision Engine for Business Data"

    # --- storage ---------------------------------------------------------
    DATA_DIR: Path = Path(_env("DECITRACE_DATA_DIR", str(ROOT_DIR / "data")))
    # SQLite is the zero-config demo default; point at PostgreSQL by setting
    # DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/decitrace
    DATABASE_URL: str = _env(
        "DATABASE_URL",
        f"sqlite:///{Path(_env('DECITRACE_DATA_DIR', str(ROOT_DIR / 'data'))) / 'decitrace.db'}",
    )

    # --- retrieval -------------------------------------------------------
    EMBEDDING_BACKEND: str = _env("EMBEDDING_BACKEND", "auto")  # auto|sentence-transformers|tfidf
    EMBEDDING_MODEL: str = _env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    VECTOR_BACKEND: str = _env("VECTOR_BACKEND", "auto")  # auto|faiss|numpy
    RAG_TOP_K: int = _env_int("RAG_TOP_K", 5)
    RAG_MIN_SCORE: float = _env_float("RAG_MIN_SCORE", 0.05)

    # --- LLM -------------------------------------------------------------
    LLM_PROVIDER: str = _env("LLM_PROVIDER", "auto")  # auto|openai|gemini|ollama|none
    LLM_API_KEY: str = _env("LLM_API_KEY", "") or _env("OPENAI_API_KEY", "") or _env("GEMINI_API_KEY", "")
    LLM_MODEL: str = _env("LLM_MODEL", "gpt-4o-mini")
    LLM_BASE_URL: str = _env("LLM_BASE_URL", "")
    LLM_TIMEOUT_SECONDS: float = _env_float("LLM_TIMEOUT_SECONDS", 25.0)

    # --- decision engine -------------------------------------------------
    PRIORITY_HIGH_THRESHOLD: float = _env_float("PRIORITY_HIGH_THRESHOLD", 55.0)
    PRIORITY_MEDIUM_THRESHOLD: float = _env_float("PRIORITY_MEDIUM_THRESHOLD", 32.0)

    # --- misc ------------------------------------------------------------
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in _env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
        ).split(",")
        if o.strip()
    ]
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")

    @property
    def llm_enabled(self) -> bool:
        """True only when a real remote LLM can actually be called."""
        provider = self.LLM_PROVIDER
        if provider == "none":
            return False
        if provider in {"ollama"}:
            return bool(self.LLM_BASE_URL)
        if provider == "auto":
            return bool(self.LLM_API_KEY)
        return bool(self.LLM_API_KEY)

    def ensure_dirs(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
