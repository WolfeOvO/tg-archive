"""Archive writer that streams files through an OpenList mount path."""

from __future__ import annotations

import asyncio
import os
import posixpath
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

from storage.base import CloudStorageBase, UploadResult


def _remote(root: str, path: str) -> str:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if ".." in parts:
        raise ValueError("Remote path cannot contain parent traversal")
    return "/" + posixpath.join(root.strip("/"), path.strip("/"))


class OpenListStorage(CloudStorageBase):
    def __init__(self, base_url="", username="", password="", root_path="/"):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.root_path = root_path
        self.client = None
        self.token = ""

    async def initialize(self):
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=None)
        response = await self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(payload.get("message") or "OpenList login failed")
        self.token = payload["data"]["token"]

    async def close(self):
        if self.client:
            await self.client.aclose()

    def _path(self, path):
        return _remote(self.root_path, path)

    def _headers(self):
        return {"Authorization": self.token}

    @staticmethod
    async def _file_chunks(local_path, chunk_size=1024 * 1024):
        handle = await asyncio.to_thread(open, local_path, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, chunk_size):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def upload_file(self, local_path, remote_path, mime_type=None):
        path = self._path(remote_path)
        headers = {
            **self._headers(),
            "File-Path": quote(path, safe="/"),
            "Content-Length": str(os.path.getsize(local_path)),
        }
        response = await self.client.put(
            "/api/fs/put",
            headers=headers,
            content=self._file_chunks(local_path),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(payload.get("message") or "OpenList upload failed")
        return UploadResult(
            path,
            os.path.basename(path),
            os.path.getsize(local_path),
            path=path,
        )

    async def file_exists(self, remote_path):
        response = await self.client.post(
            "/api/fs/get",
            headers=self._headers(),
            json={"path": self._path(remote_path), "password": ""},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") == 200:
            return True
        message = str(payload.get("message") or "")
        if "not found" in message.lower():
            return False
        raise RuntimeError(message or "OpenList file check failed")

    async def create_folder(self, folder_path):
        path = self._path(folder_path)
        response = await self.client.post(
            "/api/fs/mkdir",
            headers=self._headers(),
            json={"path": path},
        )
        payload = response.json()
        if payload.get("code") != 200:
            message = str(payload.get("message") or "")
            if "already exists" not in message.lower():
                raise RuntimeError(message or "OpenList mkdir failed")
        return path

    async def get_storage_info(self):
        response = await self.client.post(
            "/api/fs/list",
            headers=self._headers(),
            json={
                "path": self._path("/"),
                "password": "",
                "page": 1,
                "per_page": 1,
                "refresh": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(payload.get("message") or "OpenList storage unavailable")
        return {
            "used": 0,
            "total": 0,
            "available": 0,
            "detail": "Connected to OpenList mount",
        }
