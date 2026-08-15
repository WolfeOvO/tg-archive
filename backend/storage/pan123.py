"""123pan (123云盘) cloud storage backend.

Uses the 123pan Open API for file upload and management.
API docs: https://123yunpan.yuque.com/org-wiki-123yunpan-muaork/cr6ced
"""

import hashlib
import os
from typing import Optional

import httpx

from storage.base import CloudStorageBase, UploadResult

API_BASE = "https://open-api.123pan.com"


class Pan123Storage(CloudStorageBase):
    """123pan cloud storage backend."""

    def __init__(self, access_token: str, parent_file_id: int = 0):
        self.access_token = access_token
        self.parent_file_id = parent_file_id
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": self.access_token,
                "Platform": "open_platform",
            },
            timeout=120,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._client

    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
        mime_type: Optional[str] = None,
    ) -> UploadResult:
        file_size = os.path.getsize(local_path)
        file_name = os.path.basename(remote_path)
        parent_id = await self._ensure_folder(os.path.dirname(remote_path))

        # Upload v2: create → upload parts → complete
        with open(local_path, "rb") as f:
            content = f.read()

        # Single-step upload for files < 4MB, multipart for larger
        if file_size <= 4 * 1024 * 1024:
            return await self._single_upload(content, file_name, parent_id, file_size)
        else:
            return await self._multipart_upload(content, file_name, parent_id, file_size)

    async def _single_upload(
        self, content: bytes, file_name: str, parent_id: int, file_size: int
    ) -> UploadResult:
        """Single-step upload for small files."""
        resp = await self.client.post(
            "/api/v1/upload/create",
            json={
                "filename": file_name,
                "size": file_size,
                "parentFileID": parent_id,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Upload create failed: {data}")

        upload_url = data["data"]["presignedURL"]
        file_id = data["data"]["fileID"]

        # Upload content
        await self.client.put(upload_url, content=content)

        return UploadResult(
            file_id=str(file_id),
            file_name=file_name,
            file_size=file_size,
            md5=hashlib.md5(content).hexdigest(),
        )

    async def _multipart_upload(
        self, content: bytes, file_name: str, parent_id: int, file_size: int
    ) -> UploadResult:
        """Multipart upload for large files."""
        part_size = 4 * 1024 * 1024  # 4MB per part

        resp = await self.client.post(
            "/api/v1/upload/create",
            json={
                "filename": file_name,
                "size": file_size,
                "parentFileID": parent_id,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Upload create failed: {data}")

        upload_id = data["data"]["uploadID"]
        file_id = data["data"]["fileID"]

        # Upload parts
        parts = []
        for i in range(0, file_size, part_size):
            part_data = content[i : i + part_size]
            part_num = i // part_size + 1

            resp = await self.client.post(
                f"/api/v1/upload/{upload_id}/part/{part_num}",
                content=part_data,
            )
            part_data_resp = resp.json()
            if part_data_resp.get("code") != 0:
                raise RuntimeError(f"Part upload failed: {part_data_resp}")
            parts.append(part_num)

        # Complete upload
        resp = await self.client.post(
            f"/api/v1/upload/{upload_id}/complete",
            json={"fileID": file_id},
        )
        complete_data = resp.json()
        if complete_data.get("code") != 0:
            raise RuntimeError(f"Upload complete failed: {complete_data}")

        return UploadResult(
            file_id=str(file_id),
            file_name=file_name,
            file_size=file_size,
            md5=hashlib.md5(content).hexdigest(),
        )

    async def _ensure_folder(self, folder_path: str) -> int:
        """Ensure a folder path exists, creating intermediate folders as needed.

        Returns the folder ID.
        """
        if not folder_path or folder_path == "/":
            return self.parent_file_id

        parts = [p for p in folder_path.split("/") if p]
        current_parent = self.parent_file_id

        for part in parts:
            # List files in current parent to find existing folder
            resp = await self.client.get(
                "/api/v1/file/list",
                params={"parentFileID": current_parent, "limit": 100},
            )
            data = resp.json()

            found = False
            if data.get("code") == 0 and data.get("data", {}).get("fileList"):
                for f in data["data"]["fileList"]:
                    if f["filename"] == part and f.get("trashed") == False:
                        current_parent = f["fileID"]
                        found = True
                        break

            if not found:
                # Create folder
                resp = await self.client.post(
                    "/api/v1/file/mkdir",
                    json={"parentFileID": current_parent, "filename": part},
                )
                data = resp.json()
                if data.get("code") != 0:
                    raise RuntimeError(f"Failed to create folder '{part}': {data}")
                current_parent = data["data"]["fileID"]

        return current_parent

    async def file_exists(self, remote_path: str) -> bool:
        parent_path = os.path.dirname(remote_path)
        file_name = os.path.basename(remote_path)
        parent_id = await self._ensure_folder(parent_path)

        resp = await self.client.get(
            "/api/v1/file/list",
            params={"parentFileID": parent_id, "limit": 100},
        )
        data = resp.json()
        if data.get("code") == 0 and data.get("data", {}).get("fileList"):
            for f in data["data"]["fileList"]:
                if f["filename"] == file_name and f.get("trashed") == False:
                    return True
        return False

    async def create_folder(self, folder_path: str) -> str:
        folder_id = await self._ensure_folder(folder_path)
        return str(folder_id)

    async def get_storage_info(self) -> dict:
        resp = await self.client.get("/api/v1/user/info")
        data = resp.json()
        if data.get("code") == 0:
            info = data.get("data", {})
            return {
                "used": info.get("usedSpace", 0),
                "total": info.get("totalSpace", 0),
                "available": info.get("totalSpace", 0) - info.get("usedSpace", 0),
            }
        return {"used": 0, "total": 0, "available": 0}
