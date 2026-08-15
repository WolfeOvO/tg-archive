"""Notification channel configuration and delivery test endpoints."""

from typing import Literal

from config import settings
from core.notifications import (
    NotificationEvent,
    NotificationHub,
    NotificationSettings,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import require_auth

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationConfigUpdate(BaseModel):
    app_name: str = Field(min_length=1, max_length=80)
    events: list[NotificationEvent]
    timeout_seconds: float = Field(gt=0, le=60)
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    qq_enabled: bool = False
    qq_api_url: str = "http://127.0.0.1:3000"
    qq_access_token: str = ""
    qq_target_type: Literal["group", "private"] = "group"
    qq_target_id: str = ""
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""


def _masked(value: str) -> bool:
    return bool(value)


def _response(config: NotificationSettings) -> dict:
    return {
        "app_name": config.app_name,
        "events": sorted(event.value for event in config.events),
        "timeout_seconds": config.timeout_seconds,
        "telegram_enabled": config.telegram_enabled,
        "telegram_token_set": _masked(config.telegram_bot_token),
        "telegram_chat_id": config.telegram_chat_id,
        "discord_enabled": config.discord_enabled,
        "discord_webhook_set": _masked(config.discord_webhook_url),
        "qq_enabled": config.qq_enabled,
        "qq_api_url": config.qq_api_url,
        "qq_token_set": _masked(config.qq_access_token),
        "qq_target_type": config.qq_target_type,
        "qq_target_id": config.qq_target_id,
        "webhook_enabled": config.webhook_enabled,
        "webhook_url_set": _masked(config.webhook_url),
        "webhook_secret_set": _masked(config.webhook_secret),
    }


def _candidate(update: NotificationConfigUpdate, current: NotificationSettings) -> NotificationSettings:
    data = update.model_dump()
    # Empty secret fields mean "keep the existing value" in the settings UI.
    for field_name in (
        "telegram_bot_token",
        "discord_webhook_url",
        "qq_access_token",
        "webhook_secret",
        "webhook_url",
    ):
        if not data[field_name]:
            data[field_name] = getattr(current, field_name)
    return NotificationSettings(**data)


def _apply(config: NotificationSettings) -> None:
    settings.notification_app_name = config.app_name
    settings.notification_events = ",".join(sorted(event.value for event in config.events))
    settings.notification_timeout = config.timeout_seconds
    for channel in ("telegram", "discord", "qq", "webhook"):
        for suffix in {
            "telegram": ("enabled", "bot_token", "chat_id"),
            "discord": ("enabled", "webhook_url"),
            "qq": ("enabled", "api_url", "access_token", "target_type", "target_id"),
            "webhook": ("enabled", "url", "secret"),
        }[channel]:
            setattr(
                settings,
                f"notification_{channel}_{suffix}",
                getattr(config, f"{channel}_{suffix}"),
            )


@router.get("")
async def get_notifications(request: Request, token: str = Depends(require_auth)):
    # The persisted configuration loaded into the hub is the runtime source of
    # truth; environment settings are only the first-start fallback.
    return _response(request.app.state.notifier.config)


@router.put("")
async def update_notifications(
    update: NotificationConfigUpdate,
    request: Request,
    token: str = Depends(require_auth),
):
    try:
        config = _candidate(update, request.app.state.notifier.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _apply(config)
    request.app.state.notification_store.save(config)
    request.app.state.notifier.config = config
    return _response(config)


@router.post("/test")
async def test_notifications(request: Request, token: str = Depends(require_auth)):
    notifier: NotificationHub = request.app.state.notifier
    report = await notifier.publish(NotificationEvent.TEST, {})
    return {
        "delivered": report.delivered,
        "failed": report.failed,
        "skipped": report.skipped,
        "results": [
            {"channel": result.channel, "delivered": result.delivered, "error": result.error}
            for result in report.results
        ],
    }
