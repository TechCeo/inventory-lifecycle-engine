import asyncio
import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _connect_args() -> dict[str, int]:
    if settings.database_url.startswith(("postgresql://", "postgresql+")):
        return {"connect_timeout": settings.database_connect_timeout_seconds}
    return {}


engine = create_engine(
    settings.database_url,
    connect_args=_connect_args(),
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _warm_database_pool_sync() -> int:
    connections: list[Connection] = []
    try:
        for _ in range(settings.database_pool_size):
            connection = engine.connect()
            connections.append(connection)
            connection.execute(text("SELECT 1"))
        return len(connections)
    finally:
        for connection in reversed(connections):
            connection.close()


async def warm_database_pool() -> None:
    """Pre-open database pool connections without blocking API startup."""

    if not settings.database_pool_warmup_enabled:
        logger.info("Database pool warmup disabled")
        return

    delay_seconds = settings.database_pool_warmup_initial_delay_seconds
    for attempt in range(1, settings.database_pool_warmup_attempts + 1):
        try:
            warmed_connections = await asyncio.to_thread(_warm_database_pool_sync)
        except Exception:
            if attempt >= settings.database_pool_warmup_attempts:
                logger.warning(
                    "Database pool warmup exhausted retries",
                    extra={"attempt": attempt},
                    exc_info=True,
                )
                return

            logger.warning(
                "Database pool warmup failed; retrying",
                extra={"attempt": attempt, "next_delay_seconds": delay_seconds},
                exc_info=True,
            )
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(
                delay_seconds * 2,
                settings.database_pool_warmup_max_delay_seconds,
            )
            continue

        logger.info(
            "Database pool warmup completed",
            extra={"connections_warmed": warmed_connections},
        )
        return


def get_db() -> Generator[Session, None, None]:
    """Provide one transactional database session per request."""

    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
