"""Multi-channel archive notifications behind one small interface."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)
# httpx/httpcore include complete request URLs in INFO logs. Adapter URLs can
# embed Telegram/Discord credentials, so suppress request-line logging at the
# module seam even when the host application changes its global log level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class DestinationNotAllowed(RuntimeError):
    pass


class NotificationEvent(str, Enum):
    ARCHIVE_SUCCESS = "archive.success"
    ARCHIVE_FAILURE = "archive.failure"
    SCAN_SUMMARY = "scan.summary"
    RETRY_SUMMARY = "retry.summary"
    TEST = "test"


DEFAULT_EVENTS = {
    NotificationEvent.ARCHIVE_FAILURE,
    NotificationEvent.SCAN_SUMMARY,
    NotificationEvent.RETRY_SUMMARY,
}


def parse_events(value: str | Iterable[str | NotificationEvent]) -> set[NotificationEvent]:
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",") if item.strip()]
    else:
        values = list(value)
    return {item if isinstance(item, NotificationEvent) else NotificationEvent(item) for item in values}


def _validate_http_url(value: str, field_name: str) -> None:
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an http(s) URL")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field_name} must not contain control characters")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} must not contain credentials, query parameters, or fragments")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{field_name} contains an invalid port")


def _is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        return False
    if not isinstance(address, ipaddress.IPv6Address):
        return True

    if address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_global
    if address.sixtofour is not None:
        return address.sixtofour.is_global
    if address.teredo is not None:
        server, client = address.teredo
        return server.is_global and client.is_global

    nat64_prefixes = (
        ipaddress.ip_network("64:ff9b::/96"),
        ipaddress.ip_network("64:ff9b:1::/48"),
    )
    if any(address in prefix for prefix in nat64_prefixes):
        embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        return embedded.is_global
    return True


@dataclass(slots=True)
class NotificationSettings:
    app_name: str = "TG Archive"
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    qq_enabled: bool = False
    qq_api_url: str = "http://127.0.0.1:3000"
    qq_access_token: str = ""
    qq_target_type: str = "group"
    qq_target_id: str = ""
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""
    events: set[NotificationEvent] = field(default_factory=lambda: set(DEFAULT_EVENTS))
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        self.events = parse_events(self.events)
        _validate_http_url(self.discord_webhook_url, "discord_webhook_url")
        _validate_http_url(self.qq_api_url, "qq_api_url")
        _validate_http_url(self.webhook_url, "webhook_url")
        if self.discord_webhook_url:
            discord_url = urlparse(self.discord_webhook_url)
            if discord_url.scheme != "https":
                raise ValueError("discord_webhook_url must use https")
            host = (discord_url.hostname or "").lower()
            if host != "discord.com" and not host.endswith(".discord.com"):
                raise ValueError("discord_webhook_url must use an official discord.com host")
        if self.webhook_url and urlparse(self.webhook_url).scheme != "https":
            raise ValueError("webhook_url must use https")
        if self.qq_target_type not in {"group", "private"}:
            raise ValueError("qq_target_type must be group or private")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("timeout_seconds must be between 0 and 60")


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    channel: str
    delivered: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryReport:
    event: NotificationEvent
    results: tuple[DeliveryResult, ...] = ()
    skipped: bool = False

    @property
    def delivered(self) -> int:
        return sum(result.delivered for result in self.results)

    @property
    def failed(self) -> int:
        return sum(not result.delivered for result in self.results)


class NotificationConfigStore:
    """Atomically persists notification bindings outside the database."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, fallback: NotificationSettings) -> NotificationSettings:
        if not self.path.exists():
            return fallback
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return NotificationSettings(**data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.exception("Could not load notification configuration; using environment defaults")
            return fallback

    def save(self, config: NotificationSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            field_name: getattr(config, field_name)
            for field_name in config.__dataclass_fields__
        }
        data["events"] = sorted(event.value for event in config.events)
        fd, temporary = tempfile.mkstemp(prefix=".notifications-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class NotificationHub:
    """Formats an event once and concurrently dispatches it to configured adapters."""

    def __init__(
        self,
        config: NotificationSettings,
        client: httpx.AsyncClient | None = None,
        resolver=None,
    ):
        self.config = config
        self._client = client
        self._resolver = resolver or self._resolve_host

    async def publish(
        self, event: NotificationEvent | str, context: dict[str, Any]
    ) -> DeliveryReport:
        event = NotificationEvent(event)
        if event is not NotificationEvent.TEST and event not in self.config.events:
            return DeliveryReport(event=event, skipped=True)

        adapters = self._enabled_adapters()
        if not adapters:
            return DeliveryReport(event=event, skipped=True)

        text = self._format_message(event, context)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            results = await asyncio.gather(
                *(self._deliver(name, sender(client, event, context, text)) for name, sender in adapters),
            )
        finally:
            if owns_client:
                await client.aclose()

        report = DeliveryReport(event=event, results=tuple(results))
        if report.failed:
            logger.warning(
                "Notification %s delivered=%s failed=%s",
                event.value,
                report.delivered,
                report.failed,
            )
        return report

    def _enabled_adapters(self):
        adapters = []
        if self.config.telegram_enabled and self.config.telegram_bot_token and self.config.telegram_chat_id:
            adapters.append(("telegram", self._send_telegram))
        if self.config.discord_enabled and self.config.discord_webhook_url:
            adapters.append(("discord", self._send_discord))
        if self.config.qq_enabled and self.config.qq_api_url and self.config.qq_target_id:
            adapters.append(("qq", self._send_qq))
        if self.config.webhook_enabled and self.config.webhook_url:
            adapters.append(("webhook", self._send_webhook))
        return adapters

    async def _deliver(self, channel: str, operation) -> DeliveryResult:
        try:
            await operation
            return DeliveryResult(channel=channel, delivered=True)
        except DestinationNotAllowed:
            logger.warning("Notification destination rejected for %s", channel)
            return DeliveryResult(channel=channel, delivered=False, error="destination_not_allowed")
        except Exception:
            logger.warning("Notification delivery failed for %s", channel)
            return DeliveryResult(channel=channel, delivered=False, error="delivery_failed")

    async def _send_telegram(self, client, event, context, text) -> None:
        response = await client.post(
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
            json={"chat_id": self.config.telegram_chat_id, "text": text},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("ok") is False:
            raise RuntimeError(payload.get("description", "Telegram rejected the message"))

    async def _send_discord(self, client, event, context, text) -> None:
        safe_url, safe_headers, extensions = await self._validated_request(self.config.discord_webhook_url, allow_private=False)
        response = await client.post(
            safe_url,
            headers=safe_headers,
            extensions=extensions,
            json={"content": text, "allowed_mentions": {"parse": []}},
        )
        response.raise_for_status()

    async def _send_qq(self, client, event, context, text) -> None:
        # OneBot commonly runs on the same private Docker/LAN network. Only this
        # adapter has an explicit private-network exception.
        await self._assert_destination(self.config.qq_api_url, allow_private=True)
        target_key = "group_id" if self.config.qq_target_type == "group" else "user_id"
        endpoint = "send_group_msg" if self.config.qq_target_type == "group" else "send_private_msg"
        headers = {}
        if self.config.qq_access_token:
            headers["Authorization"] = f"Bearer {self.config.qq_access_token}"
        response = await client.post(
            f"{self.config.qq_api_url.rstrip('/')}/{endpoint}",
            headers=headers,
            json={target_key: int(self.config.qq_target_id), "message": text, "auto_escape": True},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in {None, "ok"} or payload.get("retcode", 0) != 0:
            raise RuntimeError(payload.get("wording") or payload.get("message") or "OneBot rejected the message")

    async def _send_webhook(self, client, event, context, text) -> None:
        safe_url, safe_headers, extensions = await self._validated_request(self.config.webhook_url, allow_private=False)
        body = json.dumps(
            {"event": event.value, "source": self.config.app_name, "text": text, "data": context},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        headers = {"Content-Type": "application/json", **safe_headers}
        if self.config.webhook_secret:
            digest = hmac.new(self.config.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-TG-Archive-Signature"] = f"sha256={digest}"
        response = await client.post(safe_url, content=body, headers=headers, extensions=extensions)
        response.raise_for_status()

    @staticmethod
    async def _resolve_host(host: str) -> list[str]:
        records = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
        return list({record[4][0] for record in records})

    async def _resolve_destination(self, url: str, allow_private: bool) -> tuple[str, str]:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise DestinationNotAllowed
        try:
            addresses = await asyncio.wait_for(
                self._resolver(host),
                timeout=self.config.timeout_seconds,
            )
        except TimeoutError as exc:
            raise RuntimeError("destination resolution timed out") from exc
        except OSError as exc:
            raise DestinationNotAllowed from exc
        if not addresses:
            raise DestinationNotAllowed
        if allow_private:
            return url, host
        if any(not _is_public_address(address) for address in addresses):
            raise DestinationNotAllowed
        address = addresses[0]
        netloc = f"[{address}]" if ":" in address else address
        if parsed.port:
            netloc += f":{parsed.port}"
        pinned = parsed._replace(netloc=netloc).geturl()
        return pinned, host

    async def _assert_destination(self, url: str, allow_private: bool) -> None:
        await self._resolve_destination(url, allow_private)

    async def _validated_request(self, url: str, allow_private: bool):
        pinned_url, original_host = await self._resolve_destination(url, allow_private)
        port = urlparse(url).port
        authority_host = f"[{original_host}]" if ":" in original_host else original_host
        host_header = f"{authority_host}:{port}" if port else authority_host
        return pinned_url, {"Host": host_header}, {"sni_hostname": original_host}

    def _format_message(self, event: NotificationEvent, context: dict[str, Any]) -> str:
        titles = {
            NotificationEvent.ARCHIVE_SUCCESS: "✅ 归档成功",
            NotificationEvent.ARCHIVE_FAILURE: "❌ 归档失败",
            NotificationEvent.SCAN_SUMMARY: "📡 扫描完成",
            NotificationEvent.RETRY_SUMMARY: "🔄 重试完成",
            NotificationEvent.TEST: "🔔 测试通知",
        }
        lines = [f"{titles[event]} · {self.config.app_name}"]
        labels = {
            "channel": "频道",
            "message_id": "消息",
            "file_name": "文件",
            "file_size": "大小",
            "remote_path": "位置",
            "error": "错误",
            "scanned": "扫描",
            "archived": "成功",
            "skipped": "跳过",
            "errors": "失败",
            "retried": "重试",
            "succeeded": "恢复",
            "failed": "仍失败",
        }
        for key, label in labels.items():
            value = context.get(key)
            if value is not None and value != "":
                if key == "file_size":
                    value = self._human_size(value)
                lines.append(f"{label}：{value}")
        if event is NotificationEvent.TEST:
            lines.append("渠道连接正常，可以接收归档状态。")
        return "\n".join(lines)

    @staticmethod
    def _human_size(value: Any) -> str:
        try:
            size = float(value)
        except (TypeError, ValueError):
            return str(value)
        units = ("B", "KB", "MB", "GB", "TB")
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return str(value)


def notification_settings_from_app(settings: Any) -> NotificationSettings:
    """Build notification configuration from application settings."""
    return NotificationSettings(
        app_name=settings.notification_app_name,
        telegram_enabled=settings.notification_telegram_enabled,
        telegram_bot_token=settings.notification_telegram_bot_token,
        telegram_chat_id=settings.notification_telegram_chat_id,
        discord_enabled=settings.notification_discord_enabled,
        discord_webhook_url=settings.notification_discord_webhook_url,
        qq_enabled=settings.notification_qq_enabled,
        qq_api_url=settings.notification_qq_api_url,
        qq_access_token=settings.notification_qq_access_token,
        qq_target_type=settings.notification_qq_target_type,
        qq_target_id=settings.notification_qq_target_id,
        webhook_enabled=settings.notification_webhook_enabled,
        webhook_url=settings.notification_webhook_url,
        webhook_secret=settings.notification_webhook_secret,
        events=parse_events(settings.notification_events),
        timeout_seconds=settings.notification_timeout,
    )
