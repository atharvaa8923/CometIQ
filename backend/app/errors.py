"""One error format for every endpoint.

  {"error": {"status": 404, "code": "not_found", "message": "Syllabus not found", "fields": [...]},
   "detail": "Syllabus not found",        # same message, kept for existing clients
   "request_id": "3f2a…"}

Validation errors list the offending fields; database conflicts (duplicate submissions, unique keys) become 409;
a query that exceeds the statement timeout becomes 503 with a retry hint. Unexpected errors are handled in monitoring.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed", 409: "conflict",
         413: "too_large", 415: "unsupported_media_type", 422: "validation_error", 429: "rate_limited", 500: "internal_error",
         503: "unavailable"}


def body(status: int, message: str, code: str | None = None, fields: list[dict] | None = None) -> dict:
    from .monitoring import request_id

    err = {"status": status, "code": code or CODES.get(status, "error"), "message": message}
    if fields:
        err["fields"] = fields
    return {"error": err, "detail": message, "request_id": request_id.get()}


def respond(status: int, message: str, code: str | None = None, fields: list[dict] | None = None, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(body(status, message, code, fields), status_code=status, headers=headers)


def _field_name(loc) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "form")]
    return ".".join(parts) or "request"


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        msg = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return respond(exc.status_code, msg, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = [{"field": _field_name(e.get("loc", ())), "message": e.get("msg", "Invalid value")} for e in exc.errors()]
        summary = "; ".join(f"{f['field']}: {f['message']}" for f in fields[:5])
        return respond(422, f"Please check: {summary}" if summary else "Invalid request", fields=fields)

    @app.exception_handler(IntegrityError)
    async def conflict(_: Request, exc: IntegrityError):
        import logging

        logging.getLogger("cometiq").warning("Integrity error: %s", str(exc.orig)[:300])
        return respond(409, "This conflicts with data that already exists (it may have been submitted twice). Refresh and try again.")

    @app.exception_handler(OperationalError)
    async def db_operational(_: Request, exc: OperationalError):
        import logging

        text = str(exc.orig).lower()
        if "statement timeout" in text or "canceling statement" in text or "lock timeout" in text or "database is locked" in text:
            logging.getLogger("cometiq").warning("Database timeout: %s", text[:200])
            return respond(503, "That took too long. Please try again in a moment.", code="timeout", headers={"Retry-After": "5"})
        logging.getLogger("cometiq").error("Database error: %s", text[:300])
        return respond(503, "The database is unavailable right now. Please try again in a moment.", headers={"Retry-After": "10"})
