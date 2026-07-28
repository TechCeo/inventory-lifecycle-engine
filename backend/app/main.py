import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.error_handlers import register_error_handlers
from app.api.router import api_v1_router, system_router
from app.core.config import get_settings
from app.db.session import warm_database_pool

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Starting API",
        extra={"environment": settings.app_environment, "version": settings.app_version},
    )
    database_pool_warmup_task = asyncio.create_task(warm_database_pool())
    application.state.database_pool_warmup_task = database_pool_warmup_task
    try:
        yield
    finally:
        if not database_pool_warmup_task.done():
            database_pool_warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await database_pool_warmup_task
        logger.info("Stopping API")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multi-user inventory and expiry notification service.",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def enforce_demo_read_only(request: Request, call_next):
        if (
            settings.demo_read_only
            and request.url.path.startswith(settings.api_v1_prefix)
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "This public portfolio demo is read-only. "
                        "Clone the repository to run a writable local instance."
                    )
                },
            )
        return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.cors_allow_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(system_router)
    application.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    register_error_handlers(application)
    return application


app = create_app()
