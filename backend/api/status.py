"""Status and monitoring API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from api.auth import require_auth
from database import async_session
from models import Message, TaskLog

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
async def get_status(token: str = Depends(require_auth)):
    """Get system status overview."""
    # This will be injected from main.py
    from main import archiver, scheduler

    status = await archiver.get_status()
    status["scheduler"] = {
        "running": scheduler.is_running,
        "interval": scheduler._interval,
    }
    return status


@router.get("/stats")
async def get_stats(token: str = Depends(require_auth)):
    """Get detailed statistics."""
    async with async_session() as db:
        # Messages by state
        state_counts = await db.execute(
            select(Message.state, func.count(Message.id)).group_by(Message.state)
        )
        states = {row[0]: row[1] for row in state_counts.all()}

        # Messages by channel
        channel_counts = await db.execute(
            select(Message.channel, func.count(Message.id))
            .group_by(Message.channel)
            .order_by(func.count(Message.id).desc())
        )
        channels = {row[0] or "unknown": row[1] for row in channel_counts.all()}

        # Messages by media type
        type_counts = await db.execute(
            select(Message.media_type, func.count(Message.id))
            .group_by(Message.media_type)
            .order_by(func.count(Message.id).desc())
        )
        media_types = {row[0] or "unknown": row[1] for row in type_counts.all()}

        # Total size
        total_size = await db.scalar(
            select(func.sum(Message.file_size)).where(Message.state == "done")
        )

        # Recent 7 days activity
        import time

        week_ago = time.time() - 7 * 86400
        recent_count = await db.scalar(
            select(func.count(Message.id)).where(Message.updated_at > week_ago)
        )

        return {
            "states": states,
            "channels": channels,
            "media_types": media_types,
            "total_size_bytes": total_size or 0,
            "recent_7_days": recent_count or 0,
        }


@router.get("/logs")
async def get_logs(
    limit: int = 50,
    offset: int = 0,
    level: str = None,
    token: str = Depends(require_auth),
):
    """Get operation logs."""
    async with async_session() as db:
        stmt = select(TaskLog).order_by(TaskLog.timestamp.desc())
        if level:
            stmt = stmt.where(TaskLog.level == level)
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        logs = result.scalars().all()

        total = await db.scalar(
            select(func.count(TaskLog.id)).where(
                TaskLog.level == level if level else True
            )
        )

        return {
            "logs": [
                {
                    "id": log.id,
                    "timestamp": log.timestamp,
                    "level": log.level,
                    "message": log.message,
                    "message_id": log.message_id,
                    "details": log.details,
                }
                for log in logs
            ],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }
