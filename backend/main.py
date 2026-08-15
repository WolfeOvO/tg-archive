"""TG Archive - FastAPI main application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db
from core.telegram_client import TelegramMonitor
from core.archiver import Archiver
from core.scheduler import Scheduler
from storage.base import CloudStorageBase

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        *(
            [logging.FileHandler(settings.log_file)]
            if settings.log_file
            else []
        ),
    ],
)
logger = logging.getLogger(__name__)

# Global instances (initialized in lifespan)
archiver: Archiver = None  # type: ignore
scheduler: Scheduler = None  # type: ignore
telegram_monitor: TelegramMonitor = None  # type: ignore
cloud_storage: CloudStorageBase = None  # type: ignore


def create_storage() -> CloudStorageBase:
    """Create the appropriate cloud storage backend."""
    if settings.cloud_type == "pan123":
        from storage.pan123 import Pan123Storage

        if not settings.pan123_access_token:
            logger.warning("123pan access token not set, falling back to local storage")
            from storage.local import LocalStorage

            return LocalStorage(settings.cloud_local_path)
        return Pan123Storage(
            access_token=settings.pan123_access_token,
            parent_file_id=settings.pan123_parent_file_id,
        )
    else:
        from storage.local import LocalStorage

        return LocalStorage(settings.cloud_local_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    global archiver, scheduler, telegram_monitor, cloud_storage

    logger.info("Starting TG Archive...")

    # Initialize database
    Path(settings.database_url.replace("sqlite+aiosqlite:///", "")).parent.mkdir(
        parents=True, exist_ok=True
    )
    await init_db()
    logger.info("Database initialized")

    # Initialize cloud storage
    cloud_storage = create_storage()
    await cloud_storage.initialize()
    logger.info(f"Cloud storage initialized: {settings.cloud_type}")

    # Initialize Telegram client
    if settings.tg_api_id and settings.tg_api_hash and settings.tg_session_string:
        try:
            telegram_monitor = TelegramMonitor(
                api_id=settings.tg_api_id,
                api_hash=settings.tg_api_hash,
                session_string=settings.tg_session_string,
            )
            await telegram_monitor.connect()
            logger.info("Telegram client connected")

            # Initialize archiver
            archiver = Archiver(telegram_monitor, cloud_storage)

            # Start scheduler
            scheduler = Scheduler(archiver)
            await scheduler.start()
            logger.info("Scheduler started")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram: {e}")
            logger.info("WebUI will work, but archiving is disabled")
            # Create a dummy archiver for API responses
            archiver = Archiver(None, cloud_storage)  # type: ignore
            scheduler = Scheduler(archiver)
    else:
        logger.warning("Telegram credentials not configured. Archiving disabled.")
        archiver = Archiver(None, cloud_storage)  # type: ignore
        scheduler = Scheduler(archiver)

    yield

    # Shutdown
    logger.info("Shutting down TG Archive...")
    if scheduler:
        await scheduler.stop()
    if telegram_monitor:
        await telegram_monitor.disconnect()
    if cloud_storage:
        await cloud_storage.close()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="TG Archive",
    description="Telegram channel archive to cloud storage",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
from api.auth import router as auth_router
from api.status import router as status_router
from api.tasks import router as tasks_router
from api.config import router as config_router

app.include_router(auth_router)
app.include_router(status_router)
app.include_router(tasks_router)
app.include_router(config_router)


# Serve frontend static files (after build)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        """Serve frontend for all non-API routes."""
        file_path = frontend_dist / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
