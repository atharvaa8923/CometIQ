"""Outgoing email: Resend API, SMTP, or 'log' (development — messages are logged and kept in OUTBOX)."""
import html
import logging
import smtplib
from collections import deque
from email.message import EmailMessage

import httpx

from ..config import get_settings

log = logging.getLogger("cometiq.email")
OUTBOX: deque[dict] = deque(maxlen=200)  # last messages sent with the log provider (used by tests)


def enabled() -> bool:
    return get_settings().EMAIL_PROVIDER in ("resend", "smtp")


def render(title: str, paragraphs: list[str], cta_text: str | None = None, cta_url: str | None = None) -> tuple[str, str]:
    """Branded HTML + plain-text bodies. Paragraphs are escaped."""
    body = "".join(f'<p style="margin:0 0 14px;line-height:1.5">{html.escape(p)}</p>' for p in paragraphs)
    button = (f'<p style="margin:22px 0"><a href="{html.escape(cta_url)}" style="background:#e87500;color:#fff;padding:11px 20px;'
              f'border-radius:8px;text-decoration:none;font-weight:600">{html.escape(cta_text)}</a></p>') if cta_text and cta_url else ""
    html_body = f"""<!doctype html><html><body style="margin:0;background:#f5f7f6;font-family:Arial,Helvetica,sans-serif;color:#1e293b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden">
<tr><td style="background:#0e4231;padding:18px 26px;color:#fff;font-size:20px;font-weight:800">COMET<span style="color:#ffa65c">IQ</span></td></tr>
<tr><td style="padding:26px"><h1 style="font-size:20px;margin:0 0 16px;color:#0e4231">{html.escape(title)}</h1>{body}{button}
<p style="margin:24px 0 0;font-size:12px;color:#64748b">You receive this because you have a CometIQ account. Manage email notifications in your account settings.</p>
</td></tr></table></td></tr></table></body></html>"""
    text = f"{title}\n\n" + "\n\n".join(paragraphs) + (f"\n\n{cta_text}: {cta_url}" if cta_url else "")
    return html_body, text


def send(to: str, subject: str, html_body: str, text_body: str) -> None:
    s = get_settings()
    provider = s.EMAIL_PROVIDER
    if provider == "resend":
        r = httpx.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {s.RESEND_API_KEY}"},
                       json={"from": s.EMAIL_FROM, "to": [to], "subject": subject, "html": html_body, "text": text_body})
        r.raise_for_status()
    elif provider == "smtp":
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.EMAIL_FROM, to, subject
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=20) as smtp:
            if s.SMTP_STARTTLS:
                smtp.starttls()
            if s.SMTP_USER:
                smtp.login(s.SMTP_USER, s.SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        OUTBOX.append({"to": to, "subject": subject, "text": text_body})
        log.info("EMAIL (log provider) to=%s subject=%s\n%s", to, subject, text_body)
