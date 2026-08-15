"""Configuration API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.auth import require_auth
from config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    tg_api_id: int
    tg_api_hash: str
    tg_session_set: bool
    tg_channel: str
    cloud_type: str
    cloud_local_path: str
    pan123_token_set: bool
    pan123_parent_file_id: int
    archive_batch_size: int
    retry_interval: int
    max_retries: int
    download_timeout: int


class ConfigUpdate(BaseModel):
    tg_channel: Optional[str] = None
    cloud_type: Optional[str] = None
    cloud_local_path: Optional[str] = None
    archive_batch_size: Optional[int] = None
    retry_interval: Optional[int] = None
    max_retries: Optional[int] = None
    download_timeout: Optional[int] = None


class CredentialUpdate(BaseModel):
    tg_api_id: Optional[int] = None
    tg_api_hash: Optional[str] = None
    tg_session_string: Optional[str] = None
    pan123_access_token: Optional[str] = None
    admin_password: Optional[str] = None


@router.get("", response_model=ConfigResponse)
async def get_config(token: str = Depends(require_auth)):
    """Get current configuration (secrets masked)."""
    return ConfigResponse(
        tg_api_id=settings.tg_api_id,
        tg_api_hash=settings.tg_api_hash[:8] + "***" if settings.tg_api_hash else "",
        tg_session_set=bool(settings.tg_session_string),
        tg_channel=settings.tg_channel,
        cloud_type=settings.cloud_type,
        cloud_local_path=settings.cloud_local_path,
        pan123_token_set=bool(settings.pan123_access_token),
        pan123_parent_file_id=settings.pan123_parent_file_id,
        archive_batch_size=settings.archive_batch_size,
        retry_interval=settings.retry_interval,
        max_retries=settings.max_retries,
        download_timeout=settings.download_timeout,
    )


@router.put("")
async def update_config(
    update: ConfigUpdate,
    token: str = Depends(require_auth),
):
    """Update runtime configuration."""
    updated = {}

    if update.tg_channel is not None:
        settings.tg_channel = update.tg_channel
        updated["tg_channel"] = update.tg_channel
    if update.cloud_type is not None:
        if update.cloud_type not in ("pan123", "local"):
            raise HTTPException(status_code=400, detail="Invalid cloud_type")
        settings.cloud_type = update.cloud_type
        updated["cloud_type"] = update.cloud_type
    if update.cloud_local_path is not None:
        settings.cloud_local_path = update.cloud_local_path
        updated["cloud_local_path"] = update.cloud_local_path
    if update.archive_batch_size is not None:
        settings.archive_batch_size = update.archive_batch_size
        updated["archive_batch_size"] = update.archive_batch_size
    if update.retry_interval is not None:
        settings.retry_interval = update.retry_interval
        updated["retry_interval"] = update.retry_interval
    if update.max_retries is not None:
        settings.max_retries = update.max_retries
        updated["max_retries"] = update.max_retries
    if update.download_timeout is not None:
        settings.download_timeout = update.download_timeout
        updated["download_timeout"] = update.download_timeout

    return {"updated": updated}


@router.put("/credentials")
async def update_credentials(
    update: CredentialUpdate,
    token: str = Depends(require_auth),
):
    """Update credentials (requires restart for some changes)."""
    updated = {}

    if update.tg_api_id is not None:
        settings.tg_api_id = update.tg_api_id
        updated["tg_api_id"] = True
    if update.tg_api_hash is not None:
        settings.tg_api_hash = update.tg_api_hash
        updated["tg_api_hash"] = True
    if update.tg_session_string is not None:
        settings.tg_session_string = update.tg_session_string
        updated["tg_session_string"] = True
    if update.pan123_access_token is not None:
        settings.pan123_access_token = update.pan123_access_token
        updated["pan123_access_token"] = True
    if update.admin_password is not None:
        settings.admin_password = update.admin_password
        updated["admin_password"] = True

    return {
        "updated": updated,
        "note": "Some changes require a restart to take effect",
    }
