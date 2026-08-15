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


@pytest.mark.asyncio
async def test_empty_scan_records_explicit_mount_without_opening_adapter(monkeypatch):
    from core.archiver import Archiver

    class Telegram:
        async def get_new_messages(self, channel, last_id):
            return []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class Mounts:
        def __init__(self):
            self.selected = []

        async def adapter(self, mount_id):
            self.selected.append(mount_id)
            return object()

        def resolve(self, mount_id):
            return type("SelectedMount", (), {"id": mount_id})()

    mounts = Mounts()
    archiver = Archiver(telegram=Telegram(), storage=object(), mount_manager=mounts)

    async def last_id(db, channel):
        return 0

    monkeypatch.setattr("core.archiver.async_session", Session)
    monkeypatch.setattr(archiver, "_get_last_message_id", last_id)

    result = await archiver.scan_and_archive("@demo", mount_id="backup-s3")

    assert result["mount_id"] == "backup-s3"
    assert mounts.selected == []


@pytest.mark.asyncio
async def test_concurrent_scans_keep_their_selected_mount_adapter(monkeypatch, tmp_path):
    import asyncio

    from core.archiver import Archiver
    from core.telegram_client import MediaInfo
    from storage.base import UploadResult

    first_waiting = asyncio.Event()
    release_first = asyncio.Event()
    uploads = []

    class Storage:
        def __init__(self, name):
            self.name = name

        async def file_exists(self, path):
            return False

        async def upload_file(self, local_path, remote_path, mime_type=None):
            uploads.append((self.name, remote_path))
            return UploadResult(self.name, "file.bin", 1)

    class Mounts:
        def __init__(self):
            self.adapters = {"a": Storage("a"), "b": Storage("b")}

        async def adapter(self, mount_id):
            return self.adapters[mount_id]

        def resolve(self, mount_id):
            return type("SelectedMount", (), {"id": mount_id})()

    class Telegram:
        async def get_new_messages(self, channel, last_id):
            return [MediaInfo(1 if channel == "@a" else 2, None, "file.bin", "application/octet-stream", 1, "document", None, "2026-08-15")]

        async def download_media(self, channel, message_id, download_dir):
            path = tmp_path / f"{message_id}.bin"
            path.write_bytes(b"x")
            if channel == "@a":
                first_waiting.set()
                await release_first.wait()
            return str(path)

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, model, key): return None
        def add(self, record): record.id = record.id
        async def flush(self): return None
        async def commit(self): return None

    archiver = Archiver(Telegram(), Storage("initial"), mount_manager=Mounts())
    monkeypatch.setattr("core.archiver.async_session", Session)
    monkeypatch.setattr(archiver, "_get_last_message_id", lambda db, channel: asyncio.sleep(0, result=0))
    monkeypatch.setattr(archiver, "_log_info", lambda *args, **kwargs: asyncio.sleep(0))

    first = asyncio.create_task(archiver.scan_and_archive("@a", mount_id="a"))
    await first_waiting.wait()
    await archiver.scan_and_archive("@b", mount_id="b")
    release_first.set()
    await first

    assert sorted(name for name, _ in uploads) == ["a", "b"]
