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

    # UTD Nebula Labs API (live sections & grade distributions) — https://api.utdnebula.com
    NEBULA_API_KEY: str = ""
    NEBULA_BASE_URL: str = "https://api.utdnebula.com"

    # Optional live job sources
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""

    # Seed demo data on first start
    SEED_DEMO: bool = True
    DEMO_PASSWORD: str = "CometIQ2026!"


@lru_cache
def get_settings() -> Settings:
    return Settings()
