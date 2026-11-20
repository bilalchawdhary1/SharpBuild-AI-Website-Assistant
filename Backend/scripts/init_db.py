from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
import app.models.chunk  # noqa: F401  (importing registers the table on Base)
import app.models.lead  # noqa: F401
import app.models.rate_limit  # noqa: F401

with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    version = conn.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    print("pgvector enabled, version:", version)

# create_all only creates MISSING tables; it never alters existing ones.
Base.metadata.create_all(engine)
print("tables:", sorted(Base.metadata.tables))