"""Local filesystem storage backend."""

import hashlib
import os
import shutil
from pathlib import Path
from typing import Optional

from storage.base import CloudStorageBase, UploadResult


class LocalStorage(CloudStorageBase):
    """Store archived files on the local filesystem."""

    def __init__(self, base_path: str = "./archive_output"):
        self.base_path = Path(base_path)

    async def initialize(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
        mime_type: Optional[str] = None,
    ) -> UploadResult:
        dest = self.base_path / remote_path.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)

        file_size = dest.stat().st_size
        md5 = self._file_md5(str(dest))

        return UploadResult(
            file_id=str(dest),
            file_name=dest.name,
            file_size=file_size,
            md5=md5,
            path=str(dest),
        )

    async def file_exists(self, remote_path: str) -> bool:
        return (self.base_path / remote_path.lstrip("/")).exists()

    async def create_folder(self, folder_path: str) -> str:
        full = self.base_path / folder_path.lstrip("/")
        full.mkdir(parents=True, exist_ok=True)
        return str(full)

    async def get_storage_info(self) -> dict:
        total, used, free = shutil.disk_usage(str(self.base_path))
        return {"used": used, "total": total, "available": free}

    async def delete_file(self, remote_path: str) -> bool:
        target = self.base_path / remote_path.lstrip("/")
        if target.exists():
            target.unlink()
            return True
        return False

    @staticmethod
    def _file_md5(path: str) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
