import pytest
from core.notifications import NotificationEvent
from core.telegram_client import MediaInfo


class RecordingNotifier:
    def __init__(self):
        self.events = []

    async def publish(self, event, context):
        self.events.append((event, context))


@pytest.mark.asyncio
async def test_archiver_emits_scan_summary_after_scan(monkeypatch):
    from core.archiver import Archiver

    class Telegram:
        async def get_new_messages(self, channel, last_id):
            return []

    notifier = RecordingNotifier()
    archiver = Archiver(telegram=Telegram(), storage=object(), notifier=notifier)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    async def last_id(db, channel):
        return 0

    async def get_new_messages(channel, last_id):
        return []

    monkeypatch.setattr("core.archiver.async_session", Session)
    monkeypatch.setattr(archiver, "_get_last_message_id", last_id)

    result = await archiver.scan_and_archive("@demo")

    assert result == {"scanned": 0, "archived": 0, "skipped": 0, "errors": 0}
    assert notifier.events == [
        (NotificationEvent.SCAN_SUMMARY, {"channel": "@demo", **result})
    ]


@pytest.mark.asyncio
async def test_archive_success_is_not_published_when_done_state_commit_fails():
    class Record:
        state = "pending"
        cloud_ids = None
        updated_at = None

    class Session:
        async def get(self, model, message_id):
            return Record()

        async def commit(self):
            raise RuntimeError("database unavailable")

    class Storage:
        async def file_exists(self, path):
            return True

    notifier = RecordingNotifier()
    from core.archiver import Archiver

    archiver = Archiver(telegram=None, storage=Storage(), notifier=notifier)
    media = MediaInfo(
        message_id=42,
        grouped_id=None,
        file_name="demo.png",
        mime_type="image/png",
        file_size=128,
        media_type="photo",
        caption=None,
        date="2026-08-15T00:00:00+00:00",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await archiver._archive_message(Session(), "@demo", media)

    assert notifier.events == []
