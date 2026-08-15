import httpx
import pytest
from storage.drivers import OpenListStorage


def test_remote_path_rejects_parent_traversal():
    storage = OpenListStorage(root_path="/archive")

    with pytest.raises(ValueError, match="parent traversal"):
        storage._path("channel/../../outside.bin")


@pytest.mark.asyncio
async def test_openlist_storage_streams_file_with_async_client(tmp_path):
    source = tmp_path / "archive.bin"
    source.write_bytes(b"stream-me" * 4096)
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"code": 200, "data": {"token": "test-token"}})
        return httpx.Response(200, json={"code": 200, "data": {}})

    storage = OpenListStorage("http://openlist:5244", "admin", "password", "/archive")
    storage.client = httpx.AsyncClient(
        base_url="http://openlist:5244",
        transport=httpx.MockTransport(handler),
    )
    storage.token = "test-token"

    result = await storage.upload_file(str(source), "channel/archive.bin")

    upload = next(request for request in requests if request.url.path == "/api/fs/put")
    assert upload.content == source.read_bytes()
    assert result.file_size == source.stat().st_size
    await storage.close()


@pytest.mark.asyncio
async def test_storage_info_rejects_openlist_application_error():
    def handler(request):
        return httpx.Response(200, json={"code": 500, "message": "storage offline"})

    storage = OpenListStorage("http://openlist:5244", "admin", "password", "/archive")
    storage.client = httpx.AsyncClient(
        base_url="http://openlist:5244",
        transport=httpx.MockTransport(handler),
    )
    storage.token = "test-token"

    with pytest.raises(RuntimeError, match="storage offline"):
        await storage.get_storage_info()
    await storage.close()


@pytest.mark.asyncio
async def test_file_exists_only_swallows_not_found_errors():
    responses = iter([
        {"code": 500, "message": "object not found"},
        {"code": 500, "message": "permission denied"},
    ])
    storage = OpenListStorage(root_path="/archive")
    storage.client = httpx.AsyncClient(
        base_url="http://openlist:5244",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses))),
    )
    storage.token = "test-token"

    assert await storage.file_exists("missing.bin") is False
    with pytest.raises(RuntimeError, match="permission denied"):
        await storage.file_exists("private.bin")
    await storage.close()


@pytest.mark.asyncio
async def test_create_folder_only_swallows_already_exists_errors():
    responses = iter([
        {"code": 500, "message": "folder already exists"},
        {"code": 500, "message": "storage offline"},
    ])
    storage = OpenListStorage(root_path="/archive")
    storage.client = httpx.AsyncClient(
        base_url="http://openlist:5244",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses))),
    )
    storage.token = "test-token"

    assert await storage.create_folder("existing") == "/archive/existing"
    with pytest.raises(RuntimeError, match="storage offline"):
        await storage.create_folder("offline")
    await storage.close()
