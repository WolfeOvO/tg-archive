"""Task management API endpoints."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from api.auth import require_auth
from database import async_session
from models import Message

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class RescanRequest(BaseModel):
    channel: str = None


class RetryRequest(BaseModel):
    message_ids: list[int] = None  # None = retry all failed


@router.get("")
async def list_tasks(
    state: str = None,
    channel: str = None,
    limit: int = 50,
    offset: int = 0,
    token: str = Depends(require_auth),
):
    """List archived messages with optional filters."""
    async with async_session() as db:
        stmt = select(Message).order_by(Message.id.desc())
        count_stmt = select(func.count(Message.id))

        if state:
            stmt = stmt.where(Message.state == state)
            count_stmt = count_stmt.where(Message.state == state)
        if channel:
            stmt = stmt.where(Message.channel == channel)
            count_stmt = count_stmt.where(Message.channel == channel)

        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        messages = result.scalars().all()

        total = await db.scalar(count_stmt)

        return {
            "tasks": [
                {
                    "id": msg.id,
                    "grouped_id": msg.grouped_id,
                    "state": msg.state,
                    "channel": msg.channel,
                    "media_type": msg.media_type,
                    "file_name": msg.file_name,
                    "file_size": msg.file_size,
                    "mime_type": msg.mime_type,
                    "caption": msg.caption[:200] if msg.caption else None,
                    "cloud_ids": json.loads(msg.cloud_ids) if msg.cloud_ids else None,
                    "error": msg.error,
                    "created_at": msg.created_at,
                    "updated_at": msg.updated_at,
                }
                for msg in messages
            ],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }


@router.get("/{message_id}")
async def get_task(message_id: int, token: str = Depends(require_auth)):
    """Get detailed info about a specific message."""
    async with async_session() as db:
        msg = await db.get(Message, message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        return {
            "id": msg.id,
            "grouped_id": msg.grouped_id,
            "state": msg.state,
            "channel": msg.channel,
            "media_type": msg.media_type,
            "file_name": msg.file_name,
            "file_size": msg.file_size,
            "mime_type": msg.mime_type,
            "caption": msg.caption,
            "cloud_ids": json.loads(msg.cloud_ids) if msg.cloud_ids else None,
            "error": msg.error,
            "created_at": msg.created_at,
            "updated_at": msg.updated_at,
        }


@router.post("/rescan")
async def rescan(
    req: RescanRequest = RescanRequest(),
    token: str = Depends(require_auth),
):
    """Trigger a manual scan of the channel."""
    from main import archiver

    try:
        results = await archiver.scan_and_archive(channel=req.channel)
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry")
async def retry_tasks(
    req: RetryRequest = RetryRequest(),
    token: str = Depends(require_auth),
):
    """Retry failed messages."""
    from main import archiver

    try:
        if req.message_ids:
            # Retry specific messages
            results = {"retried": 0, "succeeded": 0, "failed": 0}
            # TODO: implement per-message retry
            raise HTTPException(
                status_code=501, detail="Per-message retry not yet implemented"
            )
        else:
            results = await archiver.retry_failed()
        return {"success": True, "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset/{message_id}")
async def reset_task(message_id: int, token: str = Depends(require_auth)):
    """Reset a failed message to pending state."""
    async with async_session() as db:
        msg = await db.get(Message, message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg.state != "error":
            raise HTTPException(
                status_code=400, detail="Only error messages can be reset"
            )

        msg.state = "pending"
        msg.error = None
        msg.updated_at = datetime.now(timezone.utc).timestamp()

        return {"success": True, "message": f"Message {message_id} reset to pending"}
