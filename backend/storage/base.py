"""Abstract base class for cloud storage backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class UploadResult:
    """Result of a file upload operation."""

    file_id: str
    file_name: str
    file_size: int
    md5: Optional[str] = None
    path: Optional[str] = None


class CloudStorageBase(ABC):
    """Base class for cloud storage implementations.

    To add a new backend:
    1. Subclass this
    2. Implement all abstract methods
    3. Register in config.py BACKENDS dict
    """

    @abstractmethod
    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
        mime_type: Optional[str] = None,
    ) -> UploadResult:
        """Upload a local file to cloud storage.

        Args:
            local_path: Path to the local file
            remote_path: Target path in cloud storage
            mime_type: MIME type of the file

        Returns:
            UploadResult with file metadata
        """
        ...

    @abstractmethod
    async def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists at the remote path."""
        ...

    @abstractmethod
    async def create_folder(self, folder_path: str) -> str:
        """Create a folder in cloud storage.

        Args:
            folder_path: Path of the folder to create

        Returns:
            Folder ID or path
        """
        ...

    @abstractmethod
    async def get_storage_info(self) -> dict:
        """Get storage usage information.

        Returns:
            Dict with 'used', 'total', 'available' in bytes
        """
        ...

    async def delete_file(self, remote_path: str) -> bool:
        """Delete a file from cloud storage. Optional."""
        return False

    async def initialize(self) -> None:
        """Initialize the storage backend (auth, connection, etc.)."""
        pass

    async def close(self) -> None:
        """Cleanup resources."""
        pass


class UnconfiguredStorage(CloudStorageBase):
    """Keeps the WebUI available until the user creates a storage mount."""

    def _error(self):
        raise RuntimeError("No storage mount configured")

    async def upload_file(self, local_path, remote_path, mime_type=None):
        self._error()

    async def file_exists(self, remote_path):
        self._error()

    async def create_folder(self, folder_path):
        self._error()

    async def get_storage_info(self):
        return {"used": 0, "total": 0, "available": 0, "detail": "No storage mount configured"}
