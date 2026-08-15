"""Configuration management for TG Archive."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram
    tg_api_id: int = Field(default=0, description="Telegram API ID")
    tg_api_hash: str = Field(default="", description="Telegram API Hash")
    tg_session_string: str = Field(default="", description="Telegram session string")
    tg_channel: str = Field(default="", description="Target channel username or ID")

    # Cloud storage
    cloud_type: str = Field(default="local", description="Cloud storage type: pan123 | local")
    cloud_local_path: str = Field(default="./archive_output", description="Local storage path")

    # 123pan
    pan123_access_token: str = Field(default="", description="123pan API access token")
    pan123_parent_file_id: int = Field(default=0, description="123pan parent folder ID")

    # OpenList storage engine (optional; exposes its full dynamic driver catalog)
    openlist_url: str = Field(default="", description="OpenList base URL")
    openlist_username: str = Field(default="", description="OpenList admin username")
    openlist_password: str = Field(default="", description="OpenList admin password")
    openlist_default_mount_id: str = Field(default="", description="Default OpenList storage ID")

    # WebUI
    admin_password: str = Field(default="changeme", description="Admin password")
    secret_key: str = Field(default="change-this-to-a-random-secret-key", description="JWT secret key")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/tg-archive.db",
        description="Database URL",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_file: str = Field(default="./data/tg-archive.log", description="Log file path")

    # Archive settings
    archive_batch_size: int = Field(default=10, description="Messages per batch scan")
    retry_interval: int = Field(default=300, description="Retry interval in seconds")
    max_retries: int = Field(default=3, description="Max retry count per message")
    download_timeout: int = Field(default=600, description="Download timeout in seconds")

    # Notifications
    notification_app_name: str = Field(default="TG Archive", description="Notification sender name")
    notification_events: str = Field(
        default="archive.failure,scan.summary,retry.summary",
        description="Comma-separated notification events",
    )
    notification_timeout: float = Field(default=10.0, description="Delivery timeout in seconds")
    notification_telegram_enabled: bool = False
    notification_telegram_bot_token: str = ""
    notification_telegram_chat_id: str = ""
    notification_discord_enabled: bool = False
    notification_discord_webhook_url: str = ""
    notification_qq_enabled: bool = False
    notification_qq_api_url: str = "http://127.0.0.1:3000"
    notification_qq_access_token: str = ""
    notification_qq_target_type: str = "group"
    notification_qq_target_id: str = ""
    notification_webhook_enabled: bool = False
    notification_webhook_url: str = ""
    notification_webhook_secret: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def data_dir(self) -> Path:
        """Ensure data directory exists."""
        path = Path(self.database_url.replace("sqlite+aiosqlite:///", "")).parent
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
