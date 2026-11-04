from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# Serverless runs many short-lived instances, so keep each instance's pool small to avoid
# exhausting the database's connection limit. prepare_threshold=None turns off server-side
# prepared statements, which break behind a transaction-mode pooler such as Neon's pooled
# connection string (the host name contains "-pooler"). Harmless everywhere else.
CONNECT_ARGS = {"prepare_threshold": None}

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
    pool_recycle=300,
    connect_args=CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
