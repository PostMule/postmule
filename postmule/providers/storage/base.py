"""
Storage provider base — Protocol for all file-storage backends.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StorageProvider(Protocol):
    """Protocol that any PostMule storage backend must satisfy."""

    def upload_pdf(
        self,
        local_path: Path,
        filename: str,
        folder_id: str,
        verify: bool = True,
    ) -> str:
        """Upload a PDF; return the remote file ID."""
        ...

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        ...

    def rename_file(self, file_id: str, new_name: str) -> None:
        ...

    def list_folder(self, folder_id: str) -> list[dict[str, str]]:
        """Return list of file metadata dicts for a folder."""
        ...

    def ensure_folder_structure(self, folders: dict[str, str]) -> dict[str, str]:
        """Create all required folders if absent; return {key: folder_id}."""
        ...

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload arbitrary bytes; return the remote file ID."""
        ...

    def delete_file(self, file_id: str) -> None:
        """Permanently delete a file by ID."""
        ...
