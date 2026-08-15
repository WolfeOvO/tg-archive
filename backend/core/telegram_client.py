"""Telegram client wrapper for channel monitoring."""

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    Document,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    DocumentAttributeAudio,
)

logger = logging.getLogger(__name__)


@dataclass
class MediaInfo:
    """Parsed media information from a Telegram message."""

    message_id: int
    grouped_id: Optional[int]
    file_name: str
    mime_type: str
    file_size: int
    media_type: str  # photo, video, document, audio
    caption: Optional[str]
    date: str  # ISO format


class TelegramMonitor:
    """Monitor a Telegram channel for new media messages."""

    def __init__(self, api_id: int, api_hash: str, session_string: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self._client: Optional[TelegramClient] = None
        self._download_dir: Optional[Path] = None

    async def connect(self) -> None:
        """Connect to Telegram."""
        self._client = TelegramClient(
            StringSession(self.session_string),
            self.api_id,
            self.api_hash,
        )
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise RuntimeError("Telegram session is not authorized")
        logger.info("Connected to Telegram")

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self._client:
            await self._client.disconnect()
            self._client = None

    @property
    def client(self) -> TelegramClient:
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._client

    async def get_channel_info(self, channel: str) -> dict:
        """Get information about a channel."""
        entity = await self.client.get_entity(channel)
        return {
            "id": entity.id,
            "title": getattr(entity, "title", str(entity)),
            "username": getattr(entity, "username", None),
            "megagroup": getattr(entity, "megagroup", False),
        }

    async def iter_messages(
        self,
        channel: str,
        min_id: int = 0,
        max_id: int = 0,
        limit: int = 100,
    ) -> AsyncIterator[MediaInfo]:
        """Iterate over media messages in a channel.

        Args:
            channel: Channel username or ID
            min_id: Minimum message ID (exclusive)
            max_id: Maximum message ID (inclusive)
            limit: Max messages to fetch

        Yields:
            MediaInfo for each media message
        """
        entity = await self.client.get_entity(channel)

        async for message in self.client.iter_messages(
            entity,
            min_id=min_id,
            max_id=max_id,
            limit=limit,
        ):
            if not message.media:
                continue

            media_info = self._parse_media(message)
            if media_info:
                yield media_info

    async def get_new_messages(
        self, channel: str, last_id: int = 0, limit: int = 50
    ) -> list[MediaInfo]:
        """Get new media messages since last_id.

        Args:
            channel: Channel username or ID
            last_id: Last processed message ID
            limit: Max messages per batch

        Returns:
            List of MediaInfo for new media messages
        """
        messages = []
        async for media_info in self.iter_messages(
            channel, min_id=last_id, limit=limit
        ):
            messages.append(media_info)
        return messages

    async def download_media(
        self,
        channel: str,
        message_id: int,
        download_dir: Optional[str] = None,
    ) -> str:
        """Download media from a specific message.

        Args:
            channel: Channel username or ID
            message_id: Message ID to download
            download_dir: Directory to save to (uses temp dir if None)

        Returns:
            Path to the downloaded file
        """
        entity = await self.client.get_entity(channel)
        message = await self.client.get_messages(entity, ids=message_id)

        if not message or not message.media:
            raise ValueError(f"Message {message_id} has no media")

        if download_dir:
            dest = Path(download_dir)
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest = Path(tempfile.mkdtemp(prefix="tg-archive-"))

        path = await self.client.download_media(message, file=str(dest))
        if not path:
            raise RuntimeError(f"Failed to download media from message {message_id}")

        logger.info(f"Downloaded message {message_id} to {path}")
        return str(path)

    @staticmethod
    def _parse_media(message) -> Optional[MediaInfo]:
        """Parse media info from a Telethon message."""
        media = message.media
        file_name = ""
        mime_type = ""
        file_size = 0
        media_type = "unknown"

        if isinstance(media, MessageMediaPhoto):
            media_type = "photo"
            mime_type = "image/jpeg"
            if media.photo:
                file_size = getattr(media.photo, "size", 0) or 0
            file_name = f"photo_{message.id}.jpg"

        elif isinstance(media, MessageMediaDocument):
            doc = media.document
            if isinstance(doc, Document):
                file_size = doc.size
                mime_type = doc.mime_type or "application/octet-stream"

                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        file_name = attr.file_name
                    elif isinstance(attr, DocumentAttributeVideo):
                        media_type = "video"
                    elif isinstance(attr, DocumentAttributeAudio):
                        media_type = "audio"

                if media_type == "unknown":
                    if mime_type.startswith("video/"):
                        media_type = "video"
                    elif mime_type.startswith("audio/"):
                        media_type = "audio"
                    elif mime_type.startswith("image/"):
                        media_type = "photo"
                    else:
                        media_type = "document"

                if not file_name:
                    ext = mime_type.split("/")[-1].split(";")[0]
                    file_name = f"{media_type}_{message.id}.{ext}"

        if not file_name:
            return None

        caption = message.text if message.text else None

        return MediaInfo(
            message_id=message.id,
            grouped_id=message.grouped_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            media_type=media_type,
            caption=caption,
            date=message.date.isoformat() if message.date else "",
        )
