"""
Local filesystem storage provider.

All files are stored in a configurable directory on the local machine.
PDFs and JSON data stay on disk — no cloud account or credentials required.

Config example:
    storage:
      providers:
        - service: local
          enabled: true
          root_dir: "C:\\ProgramData\\PostMule\\files"
          folders:
            inbox: "Inbox"
            bills: "Bills"
            notices: "Notices"
            forward_to_me: "ForwardToMe"
            personal: "Personal"
            junk: "Junk"
            needs_review: "NeedsReview"
            duplicates: "Duplicates"
            archive: "Archive"
            system: "_System"
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

log = logging.getLogger("postmule.storage.local")

SERVICE_KEY = "local"
DISPLAY_NAME = "Local Filesystem"


class LocalStorageProvider:
    """
    Local filesystem storage provider.

    All files are stored as regular directories and files on this machine.
    No cloud account or credentials are required.

    folder_id and file_id are absolute path strings on this machine.

    Args:
        root_dir: Absolute path to the top-level PostMule folder.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, file_id: str) -> Path:
        """Resolve a file_id to a Path."""
        return Path(file_id)

    @staticmethod
    def _md5(path: Path) -> str:
        h = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # StorageProvider interface
    # ------------------------------------------------------------------

    def health_check(self):
        from postmule.providers import HealthResult
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            probe = self.root_dir / ".postmule_health"
            probe.write_bytes(b"ok")
            probe.unlink()
            return HealthResult(ok=True, status="ok", message=f"Local storage at {self.root_dir}")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def ensure_folder_structure(self, folders: dict[str, str]) -> dict[str, str]:
        """
        Create all required subdirectories inside root_dir.

        Returns:
            Dict of {key: absolute_directory_path_string}.
        """
        result: dict[str, str] = {"root": str(self.root_dir)}
        for key, name in folders.items():
            folder_path = self.root_dir / name
            folder_path.mkdir(parents=True, exist_ok=True)
            result[key] = str(folder_path)
            log.debug(f"Folder ready: {folder_path}")
        return result

    def upload_pdf(
        self,
        local_path: Path,
        filename: str,
        folder_id: str,
        verify: bool = True,
    ) -> str:
        """
        Copy a PDF into the given folder.

        Returns:
            Destination file path as file_id (absolute path string).
        """
        dest_dir = Path(folder_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename

        src_md5 = self._md5(local_path) if verify else None
        shutil.copy2(local_path, dest)

        if verify:
            dest_md5 = self._md5(dest)
            if src_md5 != dest_md5:
                raise RuntimeError(
                    f"MD5 mismatch after copy: src={src_md5} dest={dest_md5} file={filename}"
                )
            log.debug(f"Uploaded (verified) {filename} → {dest}")
        else:
            log.debug(f"Uploaded {filename} → {dest}")

        return str(dest)

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """
        Write bytes to a file in the given folder.

        Returns:
            Destination file path as file_id (absolute path string).
        """
        dest_dir = Path(folder_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        dest.write_bytes(data)
        log.debug(f"Wrote {len(data)} bytes → {dest}")
        return str(dest)

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        """Move a file to a new folder."""
        src = self._resolve(file_id)
        dest_dir = Path(new_folder_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if src.exists():
            shutil.move(str(src), str(dest))
            log.debug(f"Moved {src.name} → {dest_dir}")
        else:
            log.warning(f"move_file: source not found: {src}")

    def rename_file(self, file_id: str, new_name: str) -> None:
        """Rename a file in-place."""
        src = self._resolve(file_id)
        if src.exists():
            src.rename(src.parent / new_name)
            log.debug(f"Renamed {src.name} → {new_name}")
        else:
            log.warning(f"rename_file: file not found: {src}")

    def list_folder(self, folder_id: str) -> list[dict[str, str]]:
        """Return file metadata for all files in a folder."""
        folder = Path(folder_id)
        if not folder.exists():
            return []
        return [
            {"id": str(f), "name": f.name}
            for f in sorted(folder.iterdir())
            if f.is_file()
        ]

    def delete_file(self, file_id: str) -> None:
        """
        Soft-delete: move file to a _Trash subdirectory inside root_dir.
        Nothing is permanently deleted automatically.
        """
        src = self._resolve(file_id)
        if src.exists():
            trash_dir = self.root_dir / "_Trash"
            trash_dir.mkdir(exist_ok=True)
            dest = trash_dir / src.name
            shutil.move(str(src), str(dest))
            log.info(f"Soft-deleted {src.name} → _Trash/")
        else:
            log.warning(f"delete_file: file not found: {src}")

    def download_file(self, file_id: str) -> bytes:
        """Read and return file contents."""
        return self._resolve(file_id).read_bytes()
