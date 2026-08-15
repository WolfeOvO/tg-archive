"""Core archiver logic: coordinate download → upload → record."""

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from models import Message, TaskLog
from core.telegram_client import TelegramMonitor, MediaInfo
from core.notifications import NotificationEvent
from storage.base import CloudStorageBase, UploadResult

logger = logging.getLogger(__name__)


class Archiver:
    """Orchestrates the archive pipeline: scan → download → upload → record."""

    def __init__(
        self,
        telegram: TelegramMonitor,
        storage: CloudStorageBase,
        notifier=None,
    ):
        self.telegram = telegram
        self.storage = storage
        self.notifier = notifier
        self._running = False
        self._stats = {
            "total_processed": 0,
            "total_errors": 0,
            "last_scan_time": None,
            "last_scan_count": 0,
        }

    @property
    def stats(self) -> dict:
        return self._stats.copy()

    async def scan_and_archive(self, channel: Optional[str] = None) -> dict:
        """Scan for new messages and archive them.

        Returns:
            Dict with scan results: scanned, archived, skipped, errors
        """
        channel = channel or settings.tg_channel
        if not channel:
            raise ValueError("No channel configured")

        results = {"scanned": 0, "archived": 0, "skipped": 0, "errors": 0}

        async with async_session() as db:
            # Get last processed message ID
            last_id = await self._get_last_message_id(db, channel)

            # Fetch new messages
            messages = await self.telegram.get_new_messages(channel, last_id=last_id)
            results["scanned"] = len(messages)

            for media_info in messages:
                try:
                    # Skip if already processed
                    existing = await db.get(Message, media_info.message_id)
                    if existing and existing.state == "done":
                        results["skipped"] += 1
                        continue

                    # Process the message
                    success = await self._archive_message(db, channel, media_info)
                    if success:
                        results["archived"] += 1
                    else:
                        results["errors"] += 1

                except Exception as e:
                    logger.error(f"Error archiving message {media_info.message_id}: {e}")
                    results["errors"] += 1
                    await self._log_error(db, str(e), media_info.message_id)
                    await self._notify_failure(channel, media_info, str(e))

                await db.commit()

        self._stats["last_scan_time"] = datetime.now(timezone.utc).isoformat()
        self._stats["last_scan_count"] = results["archived"]
        self._stats["total_processed"] += results["archived"]
        self._stats["total_errors"] += results["errors"]

        logger.info(f"Scan results: {results}")
        await self._notify(NotificationEvent.SCAN_SUMMARY, {"channel": channel, **results})
        return results

    async def _archive_message(
        self, db: AsyncSession, channel: str, media_info: MediaInfo
    ) -> bool:
        """Archive a single message: download → upload → record."""
        # Create or update message record
        record = await db.get(Message, media_info.message_id)
        if not record:
            record = Message(
                id=media_info.message_id,
                grouped_id=media_info.grouped_id,
                state="pending",
                channel=channel,
                media_type=media_info.media_type,
                file_size=media_info.file_size,
                file_name=media_info.file_name,
                mime_type=media_info.mime_type,
                caption=media_info.caption,
                created_at=time.time(),
            )
            db.add(record)
            await db.flush()

        # Build remote path
        date_str = media_info.date[:7] if media_info.date else "unknown"  # YYYY-MM
        channel_name = channel.lstrip("@").replace("/", "_")
        remote_dir = f"/{channel_name}/{date_str}"

        # For grouped messages, use message_id as subfolder
        if media_info.grouped_id:
            remote_dir = f"{remote_dir}/{media_info.file_name.rsplit('.', 1)[0]}_{media_info.message_id}"

        remote_path = f"{remote_dir}/{media_info.file_name}"

        # Check if already exists in cloud
        try:
            if await self.storage.file_exists(remote_path):
                record.state = "done"
                record.cloud_ids = json.dumps([{"path": remote_path, "exists": True}])
                record.updated_at = time.time()
                logger.info(f"Message {media_info.message_id} already in cloud, skipping")
                await db.commit()
                await self._notify(
                    NotificationEvent.ARCHIVE_SUCCESS,
                    {
                        "channel": channel,
                        "message_id": media_info.message_id,
                        "file_name": media_info.file_name,
                        "file_size": media_info.file_size,
                        "remote_path": remote_path,
                    },
                )
                return True
        except Exception:
            pass  # If check fails, proceed with upload

        # Download
        record.state = "downloading"
        record.updated_at = time.time()
        await db.commit()

        download_dir = tempfile.mkdtemp(prefix="tg-archive-")
        try:
            local_path = await self.telegram.download_media(
                channel, media_info.message_id, download_dir
            )
        except Exception as e:
            record.state = "error"
            record.error = f"Download failed: {e}"
            record.updated_at = time.time()
            logger.error(f"Download failed for message {media_info.message_id}: {e}")
            await self._notify_failure(channel, media_info, record.error)
            return False

        # Upload
        record.state = "uploading"
        record.updated_at = time.time()
        await db.commit()

        try:
            result = await self.storage.upload_file(
                local_path, remote_path, media_info.mime_type
            )
        except Exception as e:
            record.state = "error"
            record.error = f"Upload failed: {e}"
            record.updated_at = time.time()
            logger.error(f"Upload failed for message {media_info.message_id}: {e}")
            await self._notify_failure(channel, media_info, record.error)
            return False
        finally:
            # Cleanup temp file
            try:
                os.unlink(local_path)
                os.rmdir(download_dir)
            except OSError:
                pass

        # Save caption as markdown if exists
        if media_info.caption:
            caption_path = f"{remote_dir}/message_{media_info.message_id}.md"
            caption_file = os.path.join(download_dir, f"caption_{media_info.message_id}.md")
            try:
                os.makedirs(download_dir, exist_ok=True)
                with open(caption_file, "w") as f:
                    f.write(media_info.caption)
                caption_result = await self.storage.upload_file(caption_file, caption_path)
                result_dict = {
                    "files": [
                        {"id": result.file_id, "path": remote_path, "md5": result.md5, "size": result.file_size},
                        {"id": caption_result.file_id, "path": caption_path, "md5": caption_result.md5, "size": caption_result.file_size},
                    ]
                }
            except Exception as e:
                logger.warning(f"Failed to save caption for message {media_info.message_id}: {e}")
                result_dict = {
                    "files": [
                        {"id": result.file_id, "path": remote_path, "md5": result.md5, "size": result.file_size}
                    ]
                }
            finally:
                try:
                    os.unlink(caption_file)
                except OSError:
                    pass
        else:
            result_dict = {
                "files": [
                    {"id": result.file_id, "path": remote_path, "md5": result.md5, "size": result.file_size}
                ]
            }

        record.state = "done"
        record.cloud_ids = json.dumps(result_dict["files"])
        record.updated_at = time.time()

        await self._log_info(
            db,
            f"Archived message {media_info.message_id}: {media_info.file_name} ({media_info.file_size} bytes)",
            media_info.message_id,
        )

        logger.info(f"Archived message {media_info.message_id} → {remote_path}")
        await db.commit()
        await self._notify(
            NotificationEvent.ARCHIVE_SUCCESS,
            {
                "channel": channel,
                "message_id": media_info.message_id,
                "file_name": media_info.file_name,
                "file_size": media_info.file_size,
                "remote_path": remote_path,
            },
        )
        return True

    async def retry_failed(self) -> dict:
        """Retry all failed messages.

        Returns:
            Dict with retry results
        """
        results = {"retried": 0, "succeeded": 0, "failed": 0}

        async with async_session() as db:
            stmt = select(Message).where(Message.state == "error")
            result = await db.execute(stmt)
            messages = result.scalars().all()

            for record in messages:
                results["retried"] += 1
                try:
                    record.state = "pending"
                    record.error = None
                    record.updated_at = time.time()
                    await db.commit()

                    # Re-archive
                    channel = record.channel or settings.tg_channel
                    media_info = MediaInfo(
                        message_id=record.id,
                        grouped_id=record.grouped_id,
                        file_name=record.file_name or "",
                        mime_type=record.mime_type or "",
                        file_size=record.file_size or 0,
                        media_type=record.media_type or "unknown",
                        caption=record.caption,
                        date=datetime.fromtimestamp(record.created_at).isoformat(),
                    )
                    success = await self._archive_message(db, channel, media_info)
                    if success:
                        results["succeeded"] += 1
                    else:
                        results["failed"] += 1
                except Exception as e:
                    results["failed"] += 1
                    logger.error(f"Retry failed for message {record.id}: {e}")
                    await self._notify(
                        NotificationEvent.ARCHIVE_FAILURE,
                        {
                            "channel": record.channel or settings.tg_channel,
                            "message_id": record.id,
                            "file_name": record.file_name,
                            "file_size": record.file_size,
                            "error": str(e),
                        },
                    )

                await db.commit()

        if results["retried"]:
            await self._notify(NotificationEvent.RETRY_SUMMARY, results)
        return results

    async def _notify_failure(self, channel: str, media_info: MediaInfo, error: str) -> None:
        await self._notify(
            NotificationEvent.ARCHIVE_FAILURE,
            {
                "channel": channel,
                "message_id": media_info.message_id,
                "file_name": media_info.file_name,
                "file_size": media_info.file_size,
                "error": error,
            },
        )

    async def _notify(self, event: NotificationEvent, context: dict) -> None:
        if self.notifier is None:
            return
        try:
            await self.notifier.publish(event, context)
        except Exception:
            logger.exception("Unexpected notification error for %s", event.value)

    async def get_status(self) -> dict:
        """Get comprehensive archive status."""
        async with async_session() as db:
            total = await db.scalar(select(func.count(Message.id)))
            done = await db.scalar(
                select(func.count(Message.id)).where(Message.state == "done")
            )
            errors = await db.scalar(
                select(func.count(Message.id)).where(Message.state == "error")
            )
            pending = await db.scalar(
                select(func.count(Message.id)).where(
                    Message.state.in_(["pending", "downloading", "uploading"])
                )
            )

            # Recent activity
            recent_stmt = (
                select(TaskLog)
                .order_by(TaskLog.timestamp.desc())
                .limit(20)
            )
            recent_result = await db.execute(recent_stmt)
            recent_logs = recent_result.scalars().all()

            storage_info = {}
            try:
                storage_info = await self.storage.get_storage_info()
            except Exception:
                pass

            return {
                "messages": {
                    "total": total or 0,
                    "done": done or 0,
                    "errors": errors or 0,
                    "pending": pending or 0,
                },
                "storage": storage_info,
                "archiver": self._stats,
                "recent_logs": [
                    {
                        "timestamp": log.timestamp,
                        "level": log.level,
                        "message": log.message,
                    }
                    for log in recent_logs
                ],
            }

    async def _get_last_message_id(self, db: AsyncSession, channel: str) -> int:
        """Get the highest message ID already processed for a channel."""
        stmt = (
            select(func.max(Message.id))
            .where(Message.channel == channel)
            .where(Message.state == "done")
        )
        result = await db.scalar(stmt)
        return result or 0

    async def _log_info(self, db: AsyncSession, message: str, msg_id: Optional[int] = None):
        log = TaskLog(
            timestamp=time.time(),
            level="info",
            message=message,
            message_id=msg_id,
        )
        db.add(log)

    async def _log_error(self, db: AsyncSession, message: str, msg_id: Optional[int] = None):
        log = TaskLog(
            timestamp=time.time(),
            level="error",
            message=message,
            message_id=msg_id,
        )
        db.add(log)
