from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# Serverless runs many short-lived instances, so keep each instance's pool small to avoid
# exhausting the database's connection limit. prepare_threshold=None turns off server-side
# prepared statements, which break behind a transaction-mode pooler such as Neon's pooled
# connection string (the host name contains "-pooler"). Harmless everywhere else.
# connect_timeout makes a database that is down or still waking up fail in 10 s instead of hanging
# the request until the platform kills it. (Do not add `options=-c statement_timeout=...`: poolers
# in transaction mode reject startup options.)
CONNECT_ARGS = {"prepare_threshold": None, "connect_timeout": 10}

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_timeout=10,          # waiting for a free pooled connection: fail fast rather than 30 s
    pool_size=3,
    max_overflow=2,
    pool_recycle=300,
    connect_args=CONNECT_ARGS,
    # Database errors normally quote the SQL parameters, which for a failed lead insert means the
    # visitor's name, email and phone would end up in the logs. Hide them.
    hide_parameters=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
