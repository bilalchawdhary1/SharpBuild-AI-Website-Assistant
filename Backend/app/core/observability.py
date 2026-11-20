"""Request IDs, log redaction, JSON logs and one summary line per request. Standard library only.

 - Every log line gets the id of the request that produced it, and the response carries it in the
   `X-Request-ID` header, so a visitor's report ("it failed, id 3f9a...") finds the exact log lines.
 - Log text is scrubbed of email addresses and long digit runs (phone numbers) before it is written,
   including text inside tracebacks. This is a safety net: the code already avoids logging personal
   data, and the database engine hides SQL parameters (see db/session.py).
 - LOG_FORMAT=json writes one JSON object per line for log tools; the default stays readable text.
"""
import contextvars
import json
import logging
import re
import secrets
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NUMBER = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w])")
_UNPRINTABLE = re.compile(r"[^\x20-\x7e]")
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"

request_log = logging.getLogger("sharpbuild.request")


def new_request_id(inbound: str | None = None) -> str:
    """Reuses a caller-supplied id only if it is plain and short (it ends up in logs and headers)."""
    return inbound if inbound and _SAFE_ID.match(inbound) else secrets.token_hex(8)


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _mask_number(match: re.Match) -> str:
    found = match.group()
    digits = sum(c.isdigit() for c in found)
    return "[number]" if 9 <= digits <= 15 and not _DATE.match(found) else found    # dates are not phone numbers


def redact(text: str) -> str:
    return _NUMBER.sub(_mask_number, _EMAIL.sub("[email]", text))


class LogContextFilter(logging.Filter):
    """Adds `request_id` to every record and redacts the message and any traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        try:
            record.msg, record.args = redact(record.getMessage()), ()
            if record.exc_info and not record.exc_text:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        except Exception:        # logging must never break the request
            pass
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = record.exc_text or self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(fmt: str = "text", level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(LogContextFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))


class RequestLogMiddleware:
    """Pure ASGI (safe for streaming): assigns the request id and logs one summary line per request.
    Logs method, path and status only: no query string, headers, body or IP address."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        inbound = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode("latin-1")
        request_id = new_request_id(inbound)
        token = request_id_var.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        started, status = time.perf_counter(), 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": [*message.get("headers", []), (b"x-request-id", request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            path = _UNPRINTABLE.sub("?", scope.get("path", ""))[:120]      # no log forging via %0a in URLs
            level = logging.ERROR if status >= 500 else logging.DEBUG if path == "/health" else logging.INFO
            request_log.log(level, "request method=%s path=%s status=%d ms=%d",
                            scope.get("method", "-"), path, status, (time.perf_counter() - started) * 1000)
            request_id_var.reset(token)
