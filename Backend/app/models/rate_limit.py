from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitHit(Base):
    """One counter per (hashed visitor key, minute). Shared by every server instance, unlike memory."""
    __tablename__ = "rate_limit_hits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)     # unix minute number
    hits: Mapped[int] = mapped_column(Integer, default=0)
