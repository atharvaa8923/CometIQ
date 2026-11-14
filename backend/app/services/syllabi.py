"""Find and download official UTD syllabi (links come from Nebula section data)."""
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from . import nebula, parser

MAX_BYTES = 15 * 1024 * 1024


def allowed_url(url: str) -> bool:
    """HTTPS on an allow-listed host (default *.utdallas.edu) — prevents server-side request forgery."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    allowed = [h.strip().lower() for h in get_settings().SYLLABUS_HOSTS.split(",") if h.strip()]
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in allowed)


def find(subject: str, number: str) -> list[dict]:
    """Sections of a course that have an official syllabus link, newest term first."""
    live = nebula.course_live(subject, number)
    if not live.get("available"):
        return []
    return live.get("syllabi", [])


def download(url: str) -> tuple[str, str]:
    """Fetch a syllabus and return (filename, text). Follows redirects only within allowed hosts."""
    if not allowed_url(url):
        raise ValueError("Syllabus links must be HTTPS on an allowed UTD host")
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        for _ in range(5):
            r = client.get(url)
            if r.is_redirect:
                url = str(r.next_request.url) if r.next_request else ""
                if not allowed_url(url):
                    raise ValueError("Syllabus redirected to a host that is not allowed")
                continue
            r.raise_for_status()
            break
        else:
            raise ValueError("Too many redirects")
    data = r.content
    if len(data) > MAX_BYTES:
        raise ValueError("Syllabus file is too large")
    ctype = r.headers.get("content-type", "").lower()
    if data.startswith(b"%PDF") or "pdf" in ctype:
        ext = ".pdf"
    elif data.startswith(b"PK") or "officedocument" in ctype:
        ext = ".docx"
    else:
        ext = ".txt"
        if "html" in ctype or data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
            import re

            data = re.sub(rb"<[^>]+>", b" ", data)
    text = parser.to_text(data, ext)
    if len(text.strip()) < 200:
        raise ValueError("The syllabus has no readable text (it may be a scanned PDF)")
    name = urlparse(url).path.rsplit("/", 1)[-1] or "syllabus"
    return (name if "." in name else name + ext), text
