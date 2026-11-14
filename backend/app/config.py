"""Application settings (read from environment / .env)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR.parent / ".env"), extra="ignore")

    APP_NAME: str = "CometIQ"
    ENV: str = "development"
    # SQLite by default so it runs anywhere; set to postgresql+psycopg://... in production
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'cometiq.db'}"
    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_HOURS: int = 24
    CORS_ORIGINS: str = "http://localhost:5173"
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    MAX_UPLOAD_MB: int = 10

    # AI (optional). Without a key the built-in engine is used.
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-opus-5-5"

    # Monitoring
    SENTRY_DSN: str = ""                 # optional error tracking (sentry.io or self-hosted)
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    LOG_FORMAT: str = "text"             # "json" for log aggregators

    # Public URL of this deployment (used in email links)
    APP_URL: str = "http://localhost:8000"
    # Email: "log" (development: printed to the log), "resend" or "smtp"
    EMAIL_PROVIDER: str = "log"
    EMAIL_FROM: str = "CometIQ <no-reply@cometiq.app>"
    RESEND_API_KEY: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    PASSWORD_RESET_MINUTES: int = 30

    # Background jobs: run in-process worker threads (set TASKS_INLINE=true to run synchronously, e.g. in tests)
    TASK_WORKERS: int = 2
    TASKS_INLINE: bool = False
    # Claude cost control: max Claude calls per organization per day (0 = unlimited)
    AI_DAILY_LIMIT_PER_ORG: int = 500

    # UTD Nebula Labs API (live sections & grade distributions) — https://api.utdnebula.com
    NEBULA_API_KEY: str = ""
    NEBULA_BASE_URL: str = "https://api.utdnebula.com"
    # Hosts CometIQ may download official syllabi from (HTTPS only; protects against SSRF)
    SYLLABUS_HOSTS: str = "utdallas.edu"

    # Optional live job sources
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    USAJOBS_API_KEY: str = ""          # https://developer.usajobs.gov/apirequest/
    USAJOBS_EMAIL: str = ""            # USAJobs requires the registered email as User-Agent
    JOB_SYNC_ENABLED: bool = True      # nightly automatic sync
    JOB_SYNC_HOUR_UTC: int = 7
    JOB_SYNC_LOCATION: str = "Dallas"
    JOB_SYNC_PER_QUERY: int = 50
    JOB_EXPIRE_DAYS: int = 60          # close synced postings older than this

    # First start: SEED_DEMO=true seeds demo users (public password!) + sample jobs — for demos only.
    # Production: SEED_DEMO=false seeds the institution + catalog and a bootstrap admin from these variables.
    SEED_DEMO: bool = True
    DEMO_PASSWORD: str = "CometIQ2026!"
    ORG_NAME: str = "The University of Texas at Dallas"
    ORG_JOIN_CODE: str = ""
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    LOGIN_RATE_LIMIT: int = 10   # failed logins per email+IP per 15 minutes


def _normalize_db_url(url: str) -> str:
    """Render/Railway/Heroku give postgres:// URLs; SQLAlchemy needs an explicit driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.DATABASE_URL = _normalize_db_url(s.DATABASE_URL)
    return s
