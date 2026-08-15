"""TG Archive - FastAPI main application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db
from frontend_paths import find_frontend_dist
from core.telegram_client import TelegramMonitor
from core.archiver import Archiver
from core.notifications import (
    NotificationConfigStore,
    NotificationHub,
    notification_settings_from_app,
)
from core.scheduler import Scheduler
from storage.base import CloudStorageBase, UnconfiguredStorage
from storage.openlist_engine import OpenListEngine

# Configure logging
if settings.log_file:
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)

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
# httpx logs complete request URLs at INFO. Notification URLs can contain bot
# or webhook credentials, so request logging must never reach application logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Global instances (initialized in lifespan)
archiver: Archiver = None  # type: ignore
scheduler: Scheduler = None  # type: ignore
telegram_monitor: TelegramMonitor = None  # type: ignore
cloud_storage: CloudStorageBase = None  # type: ignore
notifier: NotificationHub = None  # type: ignore
mount_manager = None


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
    global archiver, scheduler, telegram_monitor, cloud_storage, notifier, mount_manager

    logger.info("Starting TG Archive...")

    # Initialize database
    Path(settings.database_url.replace("sqlite+aiosqlite:///", "")).parent.mkdir(
        parents=True, exist_ok=True
    )
    await init_db()
    logger.info("Database initialized")

    notification_store = NotificationConfigStore(settings.data_dir / "notifications.json")
    notifier = NotificationHub(
        notification_store.load(notification_settings_from_app(settings))
    )
    app.state.notifier = notifier
    app.state.notification_store = notification_store

    if settings.openlist_url and settings.openlist_username and settings.openlist_password:
        mount_manager = OpenListEngine(
            settings.openlist_url,
            settings.openlist_username,
            settings.openlist_password,
            state_path=settings.data_dir / "openlist-state.json",
        )
        if settings.openlist_default_mount_id and not mount_manager.default_mount_id:
            mount_manager.set_default_mount(settings.openlist_default_mount_id)
        try:
            await mount_manager.refresh()
            cloud_storage = await mount_manager.adapter() if mount_manager._mounts else UnconfiguredStorage()
            logger.info("OpenList storage engine connected: %s drivers", len(mount_manager._drivers))
        except Exception as exc:
            logger.error("OpenList storage engine unavailable: %s", exc)
            cloud_storage = UnconfiguredStorage()
    else:
        mount_manager = None
        cloud_storage = UnconfiguredStorage()
        logger.warning("OpenList storage engine not configured; mount list is empty")
    app.state.storage_engine = mount_manager

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
            archiver = Archiver(telegram_monitor, cloud_storage, notifier=notifier, mount_manager=mount_manager)

            # Start scheduler
            scheduler = Scheduler(archiver)
            await scheduler.start()
            logger.info("Scheduler started")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram: {e}")
            logger.info("WebUI will work, but archiving is disabled")
            # Create a dummy archiver for API responses
            archiver = Archiver(None, cloud_storage, notifier=notifier, mount_manager=mount_manager)  # type: ignore
            scheduler = Scheduler(archiver)
    else:
        logger.warning("Telegram credentials not configured. Archiving disabled.")
        archiver = Archiver(None, cloud_storage, notifier=notifier, mount_manager=mount_manager)  # type: ignore
        scheduler = Scheduler(archiver)

    yield

    # Shutdown
    logger.info("Shutting down TG Archive...")
    if scheduler:
        await scheduler.stop()
    if telegram_monitor:
        await telegram_monitor.disconnect()
    if mount_manager:
        await mount_manager.close()
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
from api.health import router as health_router
from api.status import router as status_router
from api.tasks import router as tasks_router
from api.config import router as config_router
from api.notifications import router as notifications_router
from api.storage import router as storage_router

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(status_router)
app.include_router(tasks_router)
app.include_router(config_router)
app.include_router(notifications_router)
app.include_router(storage_router)


frontend_dist = find_frontend_dist(Path(__file__).parent)
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
