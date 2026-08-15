"""Scheduler for periodic tasks."""

import asyncio
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class Scheduler:
    """Simple async scheduler for periodic archive scanning."""

    def __init__(self, archiver):
        self.archiver = archiver
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._interval = settings.retry_interval

    async def start(self):
        """Start the periodic scanning loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Scheduler started (interval: {self._interval}s)")

    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _loop(self):
        """Main scheduling loop."""
        while self._running:
            try:
                logger.info("Running scheduled scan...")
                results = await self.archiver.scan_and_archive()
                logger.info(f"Scheduled scan complete: {results}")

                # Also retry failed messages
                retry_results = await self.archiver.retry_failed()
                if retry_results["retried"] > 0:
                    logger.info(f"Retry results: {retry_results}")

            except Exception as e:
                logger.error(f"Scheduled scan error: {e}")

            await asyncio.sleep(self._interval)

    @property
    def is_running(self) -> bool:
        return self._running
