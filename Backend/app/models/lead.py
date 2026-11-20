from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LeadRecord(Base):
    """A visitor who chose to leave their details. Created only with explicit consent."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), default=None)
    company: Mapped[str | None] = mapped_column(String(120), default=None)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    score: Mapped[str] = mapped_column(String(10))            # hot | warm | cold, computed on the server
    need: Mapped[bool] = mapped_column(default=False)
    budget: Mapped[bool] = mapped_column(default=False)
    timeline: Mapped[bool] = mapped_column(default=False)
    source_intent: Mapped[str | None] = mapped_column(String(30), default=None)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), default="sales", server_default="sales", index=True)
    context: Mapped[str | None] = mapped_column(Text, default=None)    # visitor's own recent messages, opt-in only
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notify_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
