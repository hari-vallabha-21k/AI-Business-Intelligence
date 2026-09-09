"""Database engine, session factory and declarative base."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
# An in-memory SQLite database lives inside one connection, so a normal pool
# hands out connections with no tables in them. StaticPool keeps everyone on
# the same connection.
_is_memory = _is_sqlite and (
    ":memory:" in settings.database_url or settings.database_url.rstrip("/").endswith("sqlite:")
)

_kwargs: dict = {}
if _is_sqlite:
    _kwargs["connect_args"] = {"check_same_thread": False}
if _is_memory:
    _kwargs["poolclass"] = StaticPool

engine = create_engine(settings.database_url, future=True, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
