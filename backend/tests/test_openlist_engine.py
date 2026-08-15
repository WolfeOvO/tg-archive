import json

import httpx
import pytest
from storage.openlist_engine import OpenListEngine


@pytest.mark.asyncio
async def test_openlist_engine_normalizes_all_dynamic_driver_fields():
    payload = {
        "code": 200,
        "data": {
            "123Pan": {
                "common": [{"name": "mount_path", "type": "string", "required": True}],
                "additional": [
                    {"name": "access_token", "type": "string", "required": True},
                    {"name": "root_folder_id", "type": "string", "default": "0"},
                ],
                "config": {"name": "123Pan"},
            },
            "S3": {
                "common": [{"name": "mount_path", "type": "string", "required": True}],
                "additional": [{"name": "secret_key", "type": "string", "required": True}],
                "config": {"name": "S3"},
            },
        },
    }

    def handler(request):
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        return httpx.Response(200, json=payload)

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    drivers = await engine.list_drivers()

    assert [driver["key"] for driver in drivers] == ["123Pan", "S3"]
    assert drivers[0]["fields"][0]["key"] == "access_token"
    assert next(field for field in drivers[0]["fields"] if field["key"] == "access_token")["secret"] is True


@pytest.mark.asyncio
async def test_openlist_engine_lists_real_mounts_without_exposing_addition():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        return httpx.Response(200, json={"code": 200, "data": {"content": [{
            "id": 7, "mount_path": "/cloud", "driver": "S3", "disabled": False,
            "status": "work", "remark": "Main", "addition": '{"secret_key":"hidden"}',
        }], "total": 1}})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    mounts = await engine.list_mounts()

    assert mounts == [{
        "id": "7", "name": "Main", "mount_path": "/cloud", "driver": "S3",
        "enabled": True, "default": False, "status": "work", "config": {},
        "secret_fields_set": [],
    }]
    assert "addition" not in mounts[0]


def test_default_mount_id_persists_with_private_permissions(tmp_path):
    path = tmp_path / "openlist-state.json"
    engine = OpenListEngine("http://openlist:5244", "admin", "password", state_path=path)

    engine.set_default_mount("42")
    restored = OpenListEngine("http://openlist:5244", "admin", "password", state_path=path)

    assert restored.default_mount_id == "42"
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_public_mount_detail_masks_secrets_and_returns_non_secret_fields():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/driver/list":
            return httpx.Response(200, json={"code": 200, "data": {"S3": {
                "common": [{"name": "root_folder_path", "type": "string"}],
                "additional": [
                    {"name": "bucket", "type": "string"},
                    {"name": "secret_key", "type": "string"},
                ],
                "config": {"name": "S3"},
            }}})
        return httpx.Response(200, json={"code": 200, "data": {
            "id": 7, "mount_path": "/cloud", "driver": "S3", "disabled": False,
            "root_folder_path": "/media", "remark": "Main",
            "addition": '{"bucket":"archive","secret_key":"hidden"}',
        }})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    detail = await engine.public_mount("7")

    assert detail["config"] == {
        "root_folder_path": "/media",
        "bucket": "archive",
        "secret_key": "",
    }
    assert detail["secret_fields_set"] == ["secret_key"]


@pytest.mark.asyncio
async def test_update_mount_sends_common_fields_at_top_level_and_preserves_blank_secrets():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/driver/list":
            return httpx.Response(200, json={"code": 200, "data": {"S3": {
                "common": [{"name": "root_folder_path", "type": "string"}],
                "additional": [{"name": "secret_key", "type": "string"}],
                "config": {"name": "S3"},
            }}})
        if request.url.path == "/api/admin/storage/get":
            return httpx.Response(200, json={"code": 200, "data": {
                "id": 7, "mount_path": "/old", "driver": "S3", "disabled": False,
                "root_folder_path": "/before", "addition": '{"secret_key":"kept"}',
            }})
        if request.url.path == "/api/admin/storage/list":
            return httpx.Response(200, json={"code": 200, "data": {"content": [], "total": 0}})
        return httpx.Response(200, json={"code": 200, "data": {}})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await engine.update_mount("7", {
        "name": "Updated", "mount_path": "/new", "driver": "S3",
        "enabled": True, "default": False,
        "config": {"root_folder_path": "/after", "secret_key": ""},
    })

    update = next(request for request in requests if request.url.path == "/api/admin/storage/update")
    body = json.loads(update.content)
    assert body["root_folder_path"] == "/after"
    assert json.loads(body["addition"])["secret_key"] == "kept"
    assert not any(request.url.path == "/api/admin/storage/enable" for request in requests)


@pytest.mark.asyncio
async def test_create_mount_coerces_openlist_boolean_and_number_defaults():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/driver/list":
            return httpx.Response(200, json={"code": 200, "data": {"Local": {
                "common": [
                    {"name": "enable_sign", "type": "bool", "default": "false"},
                    {"name": "order", "type": "number", "default": "2"},
                ],
                "additional": [{"name": "thumbnail", "type": "bool", "default": "true"}],
                "config": {"name": "Local"},
            }}})
        if request.url.path == "/api/admin/storage/list":
            return httpx.Response(200, json={"code": 200, "data": {"content": [], "total": 0}})
        return httpx.Response(200, json={"code": 200, "data": {"id": 9}})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await engine.create_mount({
        "name": "Local", "mount_path": "/local", "driver": "Local",
        "enabled": True, "default": False,
        "config": {"enable_sign": "false", "order": "2", "thumbnail": "true"},
    })

    create = next(request for request in requests if request.url.path == "/api/admin/storage/create")
    body = json.loads(create.content)
    assert body["enable_sign"] is False
    assert body["order"] == 2
    assert json.loads(body["addition"])["thumbnail"] is True
    assert not any(request.url.path == "/api/admin/storage/enable" for request in requests)


@pytest.mark.asyncio
async def test_create_mount_applies_disabled_state():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/driver/list":
            return httpx.Response(200, json={"code": 200, "data": {"Local": {
                "common": [], "additional": [], "config": {"name": "Local"},
            }}})
        if request.url.path == "/api/admin/storage/list":
            return httpx.Response(200, json={"code": 200, "data": {"content": [], "total": 0}})
        if request.url.path == "/api/admin/storage/create":
            return httpx.Response(200, json={"code": 200, "data": {"id": 12}})
        return httpx.Response(200, json={"code": 200, "data": {}})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await engine.create_mount({
        "name": "Disabled", "mount_path": "/disabled", "driver": "Local",
        "enabled": False, "default": False, "config": {},
    })

    assert any(request.url.path == "/api/admin/storage/disable" for request in requests)


@pytest.mark.asyncio
async def test_update_mount_only_changes_enabled_state_when_needed():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/storage/get":
            return httpx.Response(200, json={"code": 200, "data": {
                "id": 7, "mount_path": "/local", "driver": "Local",
                "disabled": False, "addition": "{}",
            }})
        if request.url.path == "/api/admin/storage/list":
            return httpx.Response(200, json={"code": 200, "data": {"content": [], "total": 0}})
        return httpx.Response(200, json={"code": 200, "data": {}})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    engine._drivers = {"Local": {"common": [], "additional": []}}
    await engine.update_mount("7", {
        "name": "Local", "mount_path": "/local", "driver": "Local",
        "enabled": False, "default": False, "config": {},
    })

    assert any(request.url.path == "/api/admin/storage/disable" for request in requests)
    assert not any(request.url.path == "/api/admin/storage/enable" for request in requests)


@pytest.mark.asyncio
async def test_adapter_is_reused_and_closed_with_engine(monkeypatch):
    created = []

    class Adapter:
        def __init__(self, **kwargs):
            self.closed = False
            created.append(self)

        async def initialize(self):
            return None

        async def close(self):
            self.closed = True

    monkeypatch.setattr("storage.drivers.OpenListStorage", Adapter)
    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine._mounts = [{
        "id": "7", "mount_path": "/archive", "enabled": True,
        "default": True, "driver": "Local", "name": "Archive",
    }]
    engine.default_mount_id = "7"

    first = await engine.adapter("7")
    second = await engine.adapter("7")
    await engine.close()

    assert first is second
    assert len(created) == 1
    assert first.closed is True


@pytest.mark.asyncio
async def test_concurrent_adapter_initialization_creates_one_adapter(monkeypatch):
    import asyncio

    created = []
    release = asyncio.Event()

    class Adapter:
        def __init__(self, **kwargs):
            self.closed = False
            created.append(self)

        async def initialize(self):
            await release.wait()

        async def close(self):
            self.closed = True

    monkeypatch.setattr("storage.drivers.OpenListStorage", Adapter)
    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine._mounts = [{
        "id": "7", "mount_path": "/archive", "enabled": True,
        "default": True, "driver": "Local", "name": "Archive",
    }]
    engine.default_mount_id = "7"

    first = asyncio.create_task(engine.adapter("7"))
    second = asyncio.create_task(engine.adapter("7"))
    await asyncio.sleep(0)
    release.set()

    assert await first is await second
    assert len(created) == 1
    await engine.close()


@pytest.mark.asyncio
async def test_update_body_preserves_current_disabled_state():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/storage/get":
            return httpx.Response(200, json={"code": 200, "data": {
                "id": 7, "mount_path": "/local", "driver": "Local",
                "disabled": True, "addition": "{}",
            }})
        if request.url.path == "/api/admin/storage/list":
            return httpx.Response(200, json={"code": 200, "data": {"content": [], "total": 0}})
        return httpx.Response(200, json={"code": 200, "data": {}})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    engine._drivers = {"Local": {"common": [], "additional": []}}
    await engine.update_mount("7", {
        "name": "Local", "mount_path": "/local", "driver": "Local",
        "enabled": True, "default": False, "config": {},
    })

    update = next(request for request in requests if request.url.path == "/api/admin/storage/update")
    assert json.loads(update.content)["disabled"] is True


@pytest.mark.asyncio
async def test_public_mount_masks_provider_specific_secret_names():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        if request.url.path == "/api/admin/driver/list":
            return httpx.Response(200, json={"code": 200, "data": {"Git": {
                "common": [],
                "additional": [
                    {"name": "passphrase", "type": "string"},
                    {"name": "share_pwd", "type": "string"},
                    {"name": "repoPwd", "type": "string"},
                    {"name": "two_fa_code", "type": "string"},
                    {"name": "sms_code", "type": "string"},
                    {"name": "salt", "type": "string", "confidential": True},
                ],
                "config": {"name": "Git"},
            }}})
        return httpx.Response(200, json={"code": 200, "data": {
            "id": 7, "mount_path": "/git", "driver": "Git", "disabled": False,
            "addition": '{"passphrase":"a","share_pwd":"b","repoPwd":"c","two_fa_code":"d","sms_code":"e","salt":"f"}',
        }})

    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    detail = await engine.public_mount("7")

    assert all(value == "" for value in detail["config"].values())
    assert detail["secret_fields_set"] == ["passphrase", "repoPwd", "salt", "share_pwd", "sms_code", "two_fa_code"]


@pytest.mark.asyncio
async def test_update_blocks_adapter_recreation_until_new_mount_is_visible(monkeypatch):
    import asyncio

    update_started = asyncio.Event()
    release_update = asyncio.Event()
    created_roots = []

    class Adapter:
        def __init__(self, **kwargs):
            self.root_path = kwargs["root_path"]
            created_roots.append(self.root_path)

        async def initialize(self): return None
        async def close(self): return None

    monkeypatch.setattr("storage.drivers.OpenListStorage", Adapter)
    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine._drivers = {"Local": {"common": [], "additional": []}}
    engine._mounts = [{
        "id": "7", "mount_path": "/old", "enabled": True,
        "default": True, "driver": "Local", "name": "Old",
    }]
    engine.default_mount_id = "7"
    await engine.adapter("7")

    async def get_mount(mount_id):
        return {"id": 7, "mount_path": "/old", "driver": "Local", "disabled": False, "addition": {}}

    async def request(method, path, **kwargs):
        if path == "/api/admin/storage/update":
            update_started.set()
            await release_update.wait()
        return {}

    async def list_mounts():
        engine._mounts = [{
            "id": "7", "mount_path": "/new", "enabled": True,
            "default": True, "driver": "Local", "name": "New",
        }]
        return engine._mounts

    engine.get_mount = get_mount
    engine._request = request
    engine.list_mounts = list_mounts

    updating = asyncio.create_task(engine.update_mount("7", {
        "name": "New", "mount_path": "/new", "driver": "Local",
        "enabled": True, "default": True, "config": {},
    }))
    await update_started.wait()
    async def select_with_lease():
        async with engine.adapter_session("7") as adapter:
            return adapter

    selecting = asyncio.create_task(select_with_lease())
    await asyncio.sleep(0)
    assert selecting.done() is False
    release_update.set()
    await updating
    adapter = await selecting

    assert adapter.root_path == "/new"
    assert created_roots == ["/old", "/new"]


@pytest.mark.asyncio
async def test_active_adapter_lease_blocks_mount_update(monkeypatch):
    import asyncio

    entered = asyncio.Event()
    release = asyncio.Event()

    class Adapter:
        async def initialize(self): return None
        async def close(self): return None

        def __init__(self, **kwargs):
            self.root_path = kwargs["root_path"]

    monkeypatch.setattr("storage.drivers.OpenListStorage", Adapter)
    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine._drivers = {"Local": {"common": [], "additional": []}}
    engine._mounts = [{
        "id": "7", "mount_path": "/old", "enabled": True,
        "default": True, "driver": "Local", "name": "Old",
    }]
    engine.default_mount_id = "7"
    engine.get_mount = lambda mount_id: asyncio.sleep(0, result={
        "id": 7, "mount_path": "/old", "driver": "Local", "disabled": False, "addition": {},
    })
    engine._request = lambda *args, **kwargs: asyncio.sleep(0, result={})
    engine.list_mounts = lambda: asyncio.sleep(0, result=engine._mounts)

    async def archive_use():
        async with engine.adapter_session("7"):
            entered.set()
            await release.wait()

    using = asyncio.create_task(archive_use())
    await entered.wait()
    updating = asyncio.create_task(engine.update_mount("7", {
        "name": "New", "mount_path": "/new", "driver": "Local",
        "enabled": True, "default": True, "config": {},
    }))
    await asyncio.sleep(0)
    assert updating.done() is False
    release.set()
    await using
    await updating


@pytest.mark.asyncio
async def test_implicit_adapter_session_locks_fallback_mount(monkeypatch):
    class Adapter:
        async def initialize(self): return None
        async def close(self): return None

        def __init__(self, **kwargs):
            self.root_path = kwargs["root_path"]

    monkeypatch.setattr("storage.drivers.OpenListStorage", Adapter)
    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine.default_mount_id = "7"
    engine._mounts = [
        {"id": "7", "mount_path": "/old", "enabled": False, "default": True, "driver": "Local", "name": "Old"},
        {"id": "8", "mount_path": "/ready", "enabled": True, "default": False, "driver": "Local", "name": "Ready"},
    ]

    async with engine.adapter_session() as adapter:
        assert adapter.root_path == "/ready"
        assert engine._adapter_locks["8"].locked() is True
        assert engine._adapter_locks.get("", None) is None


@pytest.mark.asyncio
async def test_adapter_session_releases_lock_when_mount_becomes_disabled():
    import asyncio

    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine._mounts = [{
        "id": "7", "mount_path": "/archive", "enabled": True,
        "default": True, "driver": "Local", "name": "Archive",
    }]
    engine.default_mount_id = "7"
    lock = engine._adapter_locks.setdefault("7", asyncio.Lock())
    await lock.acquire()

    async def lease():
        async with engine.adapter_session("7"):
            pass

    waiting = asyncio.create_task(lease())
    await asyncio.sleep(0)
    engine._mounts[0]["enabled"] = False
    lock.release()

    with pytest.raises(ValueError, match="disabled"):
        await waiting
    assert lock.locked() is False


@pytest.mark.asyncio
async def test_driver_change_is_rejected_before_openlist_update():
    engine = OpenListEngine("http://openlist:5244", "admin", "password")
    engine.get_mount = lambda mount_id: __import__("asyncio").sleep(0, result={
        "id": 7, "mount_path": "/old", "driver": "Old", "disabled": False,
        "addition": {"token": "old-secret"},
    })

    with pytest.raises(ValueError, match="cannot be changed"):
        await engine.update_mount("7", {
            "name": "New", "mount_path": "/new", "driver": "New",
            "enabled": True, "default": False, "config": {},
        })


@pytest.mark.asyncio
async def test_unchecking_current_default_clears_persisted_selection(tmp_path):
    engine = OpenListEngine(
        "http://openlist:5244", "admin", "password",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 200, "data": {"content": [], "total": 0}}))),
        state_path=tmp_path / "state.json",
    )
    engine.default_mount_id = "7"
    engine.update_mount = OpenListEngine.update_mount.__get__(engine)
    engine.get_mount = lambda mount_id: __import__("asyncio").sleep(0, result={
        "id": 7, "mount_path": "/a", "driver": "Local", "disabled": False, "addition": {},
    })
    engine._drivers = {"Local": {"common": [], "additional": []}}
    engine._request = lambda *args, **kwargs: __import__("asyncio").sleep(0, result={})

    await engine.update_mount("7", {
        "name": "A", "mount_path": "/a", "driver": "Local",
        "enabled": True, "default": False, "config": {},
    })

    assert engine.default_mount_id == ""


def test_mount_id_must_be_numeric():
    engine = OpenListEngine("http://openlist:5244", "admin", "password")

    with pytest.raises(ValueError, match="Invalid mount ID"):
        engine.resolve("7&other=1")


def test_stale_persisted_default_falls_back_to_first_enabled_mount(tmp_path):
    state = tmp_path / "state.json"
    engine = OpenListEngine("http://openlist:5244", "admin", "password", state_path=state)
    engine.default_mount_id = "7"
    engine._mounts = [
        {"id": "7", "enabled": False, "mount_path": "/old", "driver": "Local", "name": "Old"},
        {"id": "8", "enabled": True, "mount_path": "/ready", "driver": "Local", "name": "Ready"},
    ]

    selected = engine.resolve()

    assert selected.id == "8"
    assert engine.default_mount_id == "8"
    assert json.loads(state.read_text())["default_mount_id"] == "8"