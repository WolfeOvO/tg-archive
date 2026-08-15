"""SQLAlchemy models for TG Archive."""

import time
from typing import Optional

from sqlalchemy import Column, Float, Integer, String, Text, Boolean, JSON
from database import Base


class Message(Base):
    """Archived message record."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=False)  # Telegram message ID
    grouped_id = Column(Integer, nullable=True, index=True)  # Grouped media ID
    state = Column(String(20), nullable=False, default="pending", index=True)
    # States: pending, downloading, uploading, done, error
    cloud_ids = Column(Text, nullable=True)  # JSON array of cloud file info
    error = Column(Text, nullable=True)
    channel = Column(String(200), nullable=True, index=True)
    media_type = Column(String(50), nullable=True)  # photo, video, document, etc.
    file_size = Column(Integer, nullable=True)
    file_name = Column(String(500), nullable=True)
    mime_type = Column(String(100), nullable=True)
    caption = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=False, default=time.time, onupdate=time.time)


class TaskLog(Base):
    """Operation log entry."""

    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Float, nullable=False, default=time.time)
    level = Column(String(10), nullable=False, default="info")  # info, warn, error
    message = Column(Text, nullable=False)
    message_id = Column(Integer, nullable=True)  # Related Telegram message ID
    details = Column(Text, nullable=True)  # JSON extra details


class SystemConfig(Base):
    """Persistent system configuration."""

    __tablename__ = "system_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(Float, nullable=False, default=time.time, onupdate=time.time)
