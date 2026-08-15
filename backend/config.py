"""Configuration management for TG Archive."""

import os
from pathlib import Path
from typing import Optional

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def data_dir(self) -> Path:
        """Ensure data directory exists."""
        path = Path(self.database_url.replace("sqlite+aiosqlite:///", "")).parent
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
