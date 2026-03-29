"""
Dropbox storage provider.

Uses the Dropbox Python SDK (dropbox package) with a long-lived access token.

Config example:
    storage:
      providers:
        - service: dropbox
          enabled: true
          root_folder: /PostMule

Notes:
  - File IDs are Dropbox path strings (e.g. "/PostMule/Bills/2025-01-01_Alice_ATT_Bill.pdf").
  - Folder IDs are Dropbox path strings (e.g. "/PostMule/Bills").
  - Integrity verification uses Dropbox's content_hash (SHA-256-based; not MD5).
    The hash is computed locally using the same algorithm Dropbox uses and compared
    against the content_hash returned by the upload API.
  - delete_file performs a hard delete via files_permanently_delete.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger("postmule.storage.dropbox")

SERVICE_KEY = "dropbox"
DISPLAY_NAME = "Dropbox"

_BLOCK_SIZE = 4 * 1024 * 1024  # 4 MB — Dropbox content_hash block size


class DropboxProvider:
    """
    Dropbox storage provider via the Dropbox Python SDK.

    Args:
        access_token: Dropbox OAuth2 access token.
        root_folder:  Top-level Dropbox folder path (default: '/PostMule').
    """

    def __init__(
        self,
        access_token: str,
        root_folder: str = "/PostMule",
    ) -> None:
        self.access_token = access_token
        self.root_folder = "/" + root_folder.strip("/")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import dropbox  # type: ignore[import]
            except ImportError:
                raise RuntimeError("dropbox is not installed. Run: pip install dropbox")
            self._client = dropbox.Dropbox(self.access_token)
        return self._client

    def health_check(self):
        """Return a HealthResult by calling the Dropbox /users/get_current_account endpoint."""
        from postmule.providers import HealthResult
        try:
            account = self._get_client().users_get_current_account()
            name = account.name.display_name if account.name else "unknown"
            return HealthResult(ok=True, status="ok", message=f"Dropbox connected ({name})")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------

    def ensure_folder_structure(self, folders: dict) -> dict:
        """
        Create all required Dropbox folders if they don't exist.

        Args:
            folders: Dict of {key: folder_name} from config.

        Returns:
            Dict of {key: dropbox_path_string}.
        """
        dbx = self._get_client()
        result: dict[str, str] = {"root": self.root_folder}

        _ensure_folder(dbx, self.root_folder)
        for key, name in folders.items():
            path = f"{self.root_folder}/{name}"
            _ensure_folder(dbx, path)
            result[key] = path
            log.debug(f"Dropbox folder ready: {path}")

        system_path = f"{self.root_folder}/_System"
        data_path = f"{system_path}/data"
        _ensure_folder(dbx, system_path)
        _ensure_folder(dbx, data_path)
        result["system"] = system_path
        result["data"] = data_path
        return result

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def upload_pdf(
        self,
        local_path: Path,
        filename: str,
        folder_id: str,
        verify: bool = True,
    ) -> str:
        """
        Upload a PDF to a Dropbox folder.

        Args:
            local_path: Local path to the PDF.
            filename:   Name to use in Dropbox.
            folder_id:  Dropbox path string (e.g. '/PostMule/Bills').
            verify:     If True, compare locally-computed content_hash against Dropbox's.

        Returns:
            Dropbox path of the uploaded file (used as file_id).
        """
        try:
            import dropbox  # type: ignore[import]
        except ImportError:
            raise RuntimeError("dropbox is not installed. Run: pip install dropbox")

        dbx = self._get_client()
        dest_path = f"{folder_id.rstrip('/')}/{filename}"
        local_hash = _content_hash_file(local_path)

        with local_path.open("rb") as f:
            meta = dbx.files_upload(
                f.read(),
                dest_path,
                mode=dropbox.files.WriteMode.overwrite,
            )
        log.info(f"Uploaded: {filename} -> Dropbox:{dest_path}")

        if verify:
            _verify_content_hash(meta.content_hash, local_hash, filename)

        return dest_path

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload arbitrary bytes to a Dropbox folder; return the Dropbox path."""
        try:
            import dropbox  # type: ignore[import]
        except ImportError:
            raise RuntimeError("dropbox is not installed. Run: pip install dropbox")

        dbx = self._get_client()
        dest_path = f"{folder_id.rstrip('/')}/{filename}"
        dbx.files_upload(data, dest_path, mode=dropbox.files.WriteMode.overwrite)
        log.info(f"Uploaded bytes: {filename} -> Dropbox:{dest_path}")
        return dest_path

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        """Move a file to a different Dropbox folder."""
        dbx = self._get_client()
        filename = file_id.rsplit("/", 1)[-1]
        new_path = f"{new_folder_id.rstrip('/')}/{filename}"
        dbx.files_move_v2(file_id, new_path, allow_ownership_transfer=False)
        log.debug(f"Moved Dropbox file: {file_id} -> {new_path}")

    def rename_file(self, file_id: str, new_name: str) -> None:
        """Rename a file in Dropbox (same folder, new name)."""
        dbx = self._get_client()
        folder = file_id.rsplit("/", 1)[0]
        new_path = f"{folder}/{new_name}"
        dbx.files_move_v2(file_id, new_path)
        log.debug(f"Renamed Dropbox file: {file_id} -> {new_path}")

    def list_folder(self, folder_id: str) -> list[dict[str, str]]:
        """
        List files in a Dropbox folder.

        Returns list of dicts with 'id' (path), 'name'.
        """
        dbx = self._get_client()
        results = []
        response = dbx.files_list_folder(folder_id)
        while True:
            for entry in response.entries:
                try:
                    import dropbox  # type: ignore[import]
                    if isinstance(entry, dropbox.files.FileMetadata):
                        results.append({"id": entry.path_lower, "name": entry.name})
                except ImportError:
                    results.append({"id": entry.path_lower, "name": entry.name})
            if not response.has_more:
                break
            response = dbx.files_list_folder_continue(response.cursor)
        return results

    def delete_file(self, file_id: str) -> None:
        """Permanently delete a file from Dropbox."""
        self._get_client().files_permanently_delete(file_id)
        log.info(f"Deleted Dropbox file: {file_id}")

    def download_file(self, file_id: str) -> bytes:
        """Download a Dropbox file by path/ID and return raw bytes."""
        _, res = self._get_client().files_download(file_id)
        return res.content


# ------------------------------------------------------------------
# Dropbox content_hash helpers
# ------------------------------------------------------------------

def _content_hash_file(path: Path) -> str:
    """
    Compute the Dropbox content_hash for a file.

    Algorithm:
      1. Split file into 4 MB blocks.
      2. SHA-256 each block.
      3. Concatenate all block hashes.
      4. SHA-256 the concatenation.
    """
    block_hashes = b""
    with path.open("rb") as f:
        while True:
            block = f.read(_BLOCK_SIZE)
            if not block:
                break
            block_hashes += hashlib.sha256(block).digest()
    return hashlib.sha256(block_hashes).hexdigest()


def _verify_content_hash(actual: str | None, expected: str, filename: str) -> None:
    """Compare locally-computed Dropbox content_hash against the API-returned value."""
    if not actual:
        log.warning(f"Dropbox returned no content_hash for '{filename}'; skipping verification")
        return
    if actual != expected:
        raise RuntimeError(
            f"Upload verification FAILED for '{filename}'.\n"
            f"Expected content_hash: {expected}\n"
            f"Dropbox content_hash:  {actual}\n"
            "The file may be corrupt. Re-uploading is recommended."
        )
    log.debug(f"Upload verified: {filename} (content_hash={actual[:12]}...)")
