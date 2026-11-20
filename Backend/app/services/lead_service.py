"""Saving a consented lead. The score is recomputed here from the conversation: the browser's
claims are never trusted, and the contact details never pass through the AI model."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.lead import LeadRecord
from app.schemas.lead import LeadRequest
from app.services.lead_notify import any_channel_enabled, notify_lead
from app.services.lead_scoring import assess_lead

logger = logging.getLogger("sharpbuild.lead")

CONSENT_VERSION = "2026-11-v1"          # bump when the wording shown next to the checkbox changes
DEDUPE_WINDOW = timedelta(minutes=10)   # a double click or retry must not create two leads
MAX_NOTIFY_ATTEMPTS = 5                 # then the lead stays in the database for manual follow-up


CONTEXT_TURNS, CONTEXT_CHARS = 3, 300


def shared_context(request: LeadRequest) -> str | None:
    """The visitor's OWN last messages, only when they ticked the share box. Assistant text is never kept."""
    if not request.share_chat:
        return None
    turns = [" ".join(t.text.split())[:CONTEXT_CHARS] for t in request.history if t.role == "user"]
    turns = [t for t in turns if t][-CONTEXT_TURNS:]
    return "\n".join(f"- {t}" for t in turns) or None


def build_record(request: LeadRequest, now: datetime | None = None) -> LeadRecord:
    now = now or datetime.now(timezone.utc)
    # Including the email makes the contact signal count, exactly like a typed-in address would.
    lead = assess_lead(f"{request.message or ''}\n{request.email}", request.history, "project_request")
    return LeadRecord(
        name=request.name, email=request.email, phone=request.phone, company=request.company,
        message=request.message, score=lead.score, need=lead.need, budget=lead.budget,
        timeline=lead.timeline, kind=request.kind, context=shared_context(request),
        source_intent="human_handoff" if request.kind == "handoff" else "project_request",
        consent_at=now, consent_version=CONSENT_VERSION, status="new",
    )


def save_lead(db: Session, request: LeadRequest, now: datetime | None = None) -> LeadRecord | None:
    """Stores the lead. Returns None (and stores nothing) for a duplicate within DEDUPE_WINDOW."""
    now = now or datetime.now(timezone.utc)
    duplicate = db.execute(
        select(LeadRecord.id)
        .where(LeadRecord.email == request.email, LeadRecord.created_at >= now - DEDUPE_WINDOW)
        .limit(1)
    ).first()
    if duplicate:
        logger.info("lead duplicate ignored")
        return None
    record = build_record(request, now)
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("lead saved id=%s score=%s", record.id, record.score)    # never name, email or phone
    return record


def retry_pending(db: Session, settings, limit: int = 20) -> dict:
    """Re-sends leads whose notification has not succeeded yet (called by the protected retry endpoint)."""
    if not any_channel_enabled(settings):
        return {"configured": False, "checked": 0, "sent": 0}
    rows = db.execute(
        select(LeadRecord)
        .where(LeadRecord.notified_at.is_(None), LeadRecord.notify_attempts < MAX_NOTIFY_ATTEMPTS)
        .order_by(LeadRecord.id)
        .limit(limit)
    ).scalars().all()
    sent = sum(1 for record in rows if notify_lead(db, record, settings))
    return {"configured": True, "checked": len(rows), "sent": sent}


def lead_stats(db: Session, settings, now: datetime | None = None) -> dict:
    """Counts for the admin stats endpoint: volume, and notifications that never went out."""
    now = now or datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    unsent = LeadRecord.notified_at.is_(None)
    total, last_24h, handoff_24h, pending, gave_up = db.execute(select(
        func.count(LeadRecord.id),
        func.count(LeadRecord.id).filter(LeadRecord.created_at >= day_ago),
        func.count(LeadRecord.id).filter(LeadRecord.created_at >= day_ago, LeadRecord.kind == "handoff"),
        func.count(LeadRecord.id).filter(unsent, LeadRecord.notify_attempts < MAX_NOTIFY_ATTEMPTS),
        func.count(LeadRecord.id).filter(unsent, LeadRecord.notify_attempts >= MAX_NOTIFY_ATTEMPTS),
    )).one()
    return {
        "leads": {"total": total, "last_24h": last_24h, "handoff_last_24h": handoff_24h},
        # "pending" means: not delivered yet and still being retried. "gave_up" needs a person.
        "notifications": {"configured": any_channel_enabled(settings), "pending": pending, "gave_up": gave_up},
    }
