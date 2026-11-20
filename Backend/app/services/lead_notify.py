"""Delivers a saved lead to the business: a signed webhook (any CRM / Zapier / Make) and/or an email.

Standard library only. Failure of either channel never affects the visitor: the lead is already
saved, `notified_at` stays empty, and the retry endpoint picks it up later.

Webhook security: HTTPS only, no redirects, body signed with HMAC-SHA256:
    X-SharpBuild-Timestamp: <unix seconds>
    X-SharpBuild-Signature: sha256=hex(HMAC(secret, "<timestamp>." + raw_body))
Receivers should reject old timestamps and de-duplicate on payload["id"] (a retry may re-send).
Logs never contain the URL, the secret, or any personal detail.
"""
import hmac
import json
import logging
import smtplib
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

logger = logging.getLogger("sharpbuild.notify")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None                                   # a redirect is treated as a failure (HTTPError)


_opener = urllib.request.build_opener(_NoRedirect)


def webhook_enabled(settings) -> bool:
    return settings.lead_webhook_url.startswith("https://") and bool(settings.lead_webhook_secret)


def email_enabled(settings) -> bool:
    return bool(settings.smtp_host and settings.lead_email_to and settings.lead_email_from)


def any_channel_enabled(settings) -> bool:
    return webhook_enabled(settings) or email_enabled(settings)


def lead_payload(record) -> dict:
    created = getattr(record, "created_at", None)
    return {
        "id": record.id,
        "source": "sharpbuild-assistant",
        "created_at": created.isoformat() if created else None,
        "name": record.name,
        "email": record.email,
        "phone": record.phone,
        "company": record.company,
        "message": record.message,
        "kind": getattr(record, "kind", None) or "sales",                 # "handoff" = asked to talk to a person: answer first
        "context": getattr(record, "context", None),                      # visitor's recent messages, only if they opted in
        "score": record.score,
        "signals": {"need": record.need, "budget": record.budget, "timeline": record.timeline},
        "consent": {"given_at": record.consent_at.isoformat(), "version": record.consent_version},
    }


def sign(body: bytes, secret: str, timestamp: str) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, "sha256").hexdigest()
    return f"sha256={digest}"


def send_webhook(payload: dict, url: str, secret: str, timeout: float, opener=_opener.open, now=time.time) -> None:
    """Raises on any failure (network error, non-2xx, redirect)."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(now()))
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SharpBuild-Assistant/1",
            "X-SharpBuild-Timestamp": timestamp,
            "X-SharpBuild-Signature": sign(body, secret, timestamp),
        },
    )
    with opener(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"webhook returned {response.status}")


def _one_line(value: str | None, limit: int = 120) -> str:
    return " ".join((value or "").split())[:limit]          # no line breaks: blocks header injection


def send_email(record, settings, smtp_factory=smtplib.SMTP, smtp_ssl_factory=smtplib.SMTP_SSL) -> None:
    message = EmailMessage()
    kind, context = getattr(record, "kind", None) or "sales", getattr(record, "context", None)
    title = "HANDOFF REQUEST" if kind == "handoff" else f"New {record.score} lead"
    message["Subject"] = f"{title}: {_one_line(record.name, 60)}"
    message["From"] = settings.lead_email_from
    message["To"] = settings.lead_email_to
    message["Reply-To"] = record.email
    message.set_content("\n".join([
        "Type: the visitor asked to talk to a person" if kind == "handoff" else "Type: sales enquiry",
        f"Score: {record.score} (need={record.need}, budget={record.budget}, timeline={record.timeline})",
        f"Name: {_one_line(record.name)}",
        f"Email: {record.email}",
        f"Phone: {_one_line(record.phone) or '-'}",
        f"Company: {_one_line(record.company) or '-'}",
        "",
        "Message:",
        record.message or "-",
        "",
        "Recent messages from the visitor (shared by them):" if context else "Chat context: not shared",
        *([context] if context else []),
        "",
        f"Lead id: {record.id}. Consent recorded {record.consent_at.isoformat()} ({record.consent_version}).",
    ]))
    timeout = settings.notify_timeout_seconds
    if settings.smtp_port == 465:
        server = smtp_ssl_factory(settings.smtp_host, 465, timeout=timeout, context=ssl.create_default_context())
    else:
        server = smtp_factory(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with server:
        if settings.smtp_port != 465:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def notify_lead(db, record, settings) -> bool:
    """Runs every configured channel once. True only if all configured channels succeeded.
    Never raises. Marks the record notified on success and counts the attempt otherwise."""
    if not any_channel_enabled(settings):
        return False
    results: dict[str, bool] = {}
    if webhook_enabled(settings):
        try:
            send_webhook(lead_payload(record), settings.lead_webhook_url, settings.lead_webhook_secret,
                         settings.notify_timeout_seconds)
            results["webhook"] = True
        except Exception as error:
            logger.warning("lead notify webhook failed id=%s error=%s", record.id, type(error).__name__)
            results["webhook"] = False
    if email_enabled(settings):
        try:
            send_email(record, settings)
            results["email"] = True
        except Exception as error:
            logger.warning("lead notify email failed id=%s error=%s", record.id, type(error).__name__)
            results["email"] = False
    ok = all(results.values())
    try:
        record.notify_attempts = (record.notify_attempts or 0) + 1
        if ok:
            record.notified_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        logger.exception("lead notify bookkeeping failed id=%s", record.id)
        try:
            db.rollback()
        except Exception:
            pass
    logger.info("lead notify id=%s %s", record.id, " ".join(f"{k}={'ok' if v else 'failed'}" for k, v in results.items()))
    return ok
