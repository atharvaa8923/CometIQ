"""Thin wrapper around the Claude API.

Every AI feature in CometIQ has a deterministic built-in fallback, so the platform
works without a key. With ANTHROPIC_API_KEY set, calls go to Claude and return
schema-validated Pydantic objects (structured outputs).
"""
import logging
from typing import TypeVar

from pydantic import BaseModel

from ..config import get_settings

log = logging.getLogger("cometiq.ai")
T = TypeVar("T", bound=BaseModel)
_client = None


def enabled() -> bool:
    return bool(get_settings().ANTHROPIC_API_KEY)


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=get_settings().ANTHROPIC_API_KEY, max_retries=2, timeout=300)
    return _client


def _within_cap() -> bool:
    """Count this call against the organization's daily Claude budget (AI_DAILY_LIMIT_PER_ORG)."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..db import SessionLocal
    from ..models import AiUsage
    from .tasks import current_org

    limit, org = get_settings().AI_DAILY_LIMIT_PER_ORG, current_org.get()
    if not limit or not org:
        return True
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with SessionLocal() as db:
        row = db.scalar(select(AiUsage).where(AiUsage.org_id == org, AiUsage.day == day))
        if row and row.calls >= limit:
            return False
        if row:
            row.calls += 1
        else:
            db.add(AiUsage(org_id=org, day=day, calls=1))
        try:
            db.commit()
        except Exception:  # concurrent first insert for the day
            db.rollback()
    return True


def structured(system: str, prompt: str, schema: type[T], effort: str = "medium",
               max_tokens: int = 32000) -> T | None:
    """Ask Claude for a response matching `schema`. Returns None on any failure
    (missing key, API error, refusal) so callers fall back to the built-in engine."""
    if not enabled():
        return None
    if not _within_cap():
        log.warning("Daily Claude limit reached for this organization; using built-in engine")
        return None
    try:
        import anthropic

        settings = get_settings()
        with _get_client().beta.messages.stream(
            model=settings.AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
            # Server-side refusal fallback: re-runs on a fallback model if declined.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            log.warning("Claude declined the request; using built-in engine")
            return None
        if msg.stop_reason == "max_tokens":
            log.warning("Claude output hit max_tokens; using built-in engine")
            return None
        return msg.parsed_output
    except anthropic.RateLimitError as e:
        log.warning("Claude rate limited: %s", e)
    except anthropic.APIStatusError as e:
        log.error("Claude API error %s: %s", e.status_code, e.message)
    except anthropic.APIConnectionError as e:
        log.error("Claude connection error: %s", e)
    except Exception as e:  # validation / unexpected — never break the request
        log.exception("Claude call failed: %s", e)
    return None
