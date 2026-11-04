from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Must match the embedding model's output size (text-embedding-3-small -> 1536).
EMBEDDING_DIMS = 1536


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # hash of url+content
    url: Mapped[str] = mapped_column(String(500), index=True)
    title: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(Text, default="")
    page_type: Mapped[str] = mapped_column(String(50), index=True)
    chunk_index: Mapped[int]
    word_count: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    embedding_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())