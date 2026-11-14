"""Turn uploaded PDF / DOCX / TXT files into plain text, and pull topic lines from syllabi."""
import io
import re

from fastapi import HTTPException, UploadFile

from ..config import get_settings

ALLOWED = {".pdf", ".docx", ".txt", ".md"}


async def read_upload(file: UploadFile) -> tuple[str, str]:
    name = file.filename or "upload.txt"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'}. Use PDF, DOCX or TXT.")
    data = await file.read()
    if len(data) > get_settings().MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")
    try:
        text = to_text(data, ext)
    except Exception as e:
        raise HTTPException(422, f"Could not read file: {e}")
    if len(text.strip()) < 20:
        raise HTTPException(422, "No readable text found in the file (scanned PDFs are not supported).")
    return name, text


def to_text(data: bytes, ext: str) -> str:
    if ext == ".pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    if ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    return data.decode("utf-8", errors="ignore")


_TOPIC = re.compile(r"^\s*(?:week|wk|module|session|unit|lecture|class|topic|day)\s*[#:]?\s*\d+\s*[:.\-–—)|]*\s*(.+)$", re.I)
_DATE = re.compile(r"^\s*(?:\d{1,2}/\d{1,2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2})\s*[:\-–—|]?\s*(.{6,})$", re.I)


def extract_topics(text: str, limit: int = 40) -> list[str]:
    topics: list[str] = []
    for line in text.splitlines():
        m = _TOPIC.match(line) or _DATE.match(line)
        if m:
            t = " ".join(m.group(1).split()).strip(" -–|:")
            if 4 <= len(t) <= 160 and t not in topics:
                topics.append(t)
        if len(topics) >= limit:
            break
    return topics
