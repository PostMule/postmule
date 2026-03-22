"""
Google Drive storage provider.

Responsibilities:
  - Create/find folders in Drive
  - Upload files (PDFs)
  - Move files between folders
  - Download files
  - List folder contents
  - MD5 checksum verification via Drive metadata (no full download needed)
"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.storage.drive")

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveProvider:
    """
    Google Drive API provider.

    Args:
        credentials: google.oauth2.credentials.Credentials object (from build_google_credentials()).
        root_folder:  Name of the top-level PostMule folder in Drive.
    """

    def __init__(self, credentials: Any, root_folder: str = "PostMule") -> None:
        self.credentials = credentials
        self.root_folder = root_folder
        self._service = None
        self._folder_cache: dict[str, str] = {}  # path -> Drive file ID

    def _get_service(self):
        if self._service is None:
            from googleapiclient.discovery import build  # type: ignore[import]
            self._service = build("drive", "v3", credentials=self.credentials)
        return self._service

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------

    def ensure_folder_structure(self, folders: dict[str, str]) -> dict[str, str]:
        """
        Create all PostMule folders in Drive if they don't exist.

        Args:
            folders: Dict of {key: folder_name} from config.

        Returns:
            Dict of {key: drive_folder_id}.
        """
        root_id = self._get_or_create_folder(self.root_folder, parent_id=None)
        self._folder_cache["root"] = root_id

        result = {"root": root_id}
        for key, name in folders.items():
            folder_id = self._get_or_create_folder(name, parent_id=root_id)
            self._folder_cache[key] = folder_id
            result[key] = folder_id
            log.debug(f"Folder ready: {name} ({folder_id})")

        # System/data subfolder
        system_id = self._get_or_create_folder("_System", parent_id=root_id)
        data_id = self._get_or_create_folder("data", parent_id=system_id)
        result["system"] = system_id
        result["data"] = data_id

        return result

    def _get_or_create_folder(self, name: str, parent_id: str | None) -> str:
        svc = self._get_service()
        query = f"name='{name}' and mimeType='{_FOLDER_MIME}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = svc.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        body: dict[str, Any] = {
            "name": name,
            "mimeType": _FOLDER_MIME,
        }
        if parent_id:
            body["parents"] = [parent_id]

        folder = svc.files().create(body=body, fields="id").execute()
        log.info(f"Created Drive folder: {name}")
        return folder["id"]

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
        Upload a PDF file to a Drive folder.

        Args:
            local_path: Local path to the PDF.
            filename:   Name to use in Drive.
            folder_id:  Drive folder ID to upload into.
            verify:     If True, compare local MD5 against Drive's md5Checksum metadata.

        Returns:
            Drive file ID of the uploaded file.
        """
        from googleapiclient.http import MediaFileUpload  # type: ignore[import]

        svc = self._get_service()
        metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(str(local_path), mimetype="application/pdf", resumable=True)

        file = svc.files().create(
            body=metadata,
            media_body=media,
            fields="id, name, size",
        ).execute()

        file_id = file["id"]
        log.info(f"Uploaded: {filename} -> Drive ({file_id})")

        if verify:
            local_md5 = _md5_file(local_path)
            self._verify_upload(file_id, local_md5, filename)

        return file_id

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        """Move a file from one Drive folder to another."""
        svc = self._get_service()
        svc.files().update(
            fileId=file_id,
            addParents=new_folder_id,
            removeParents=old_folder_id,
            fields="id, parents",
        ).execute()
        log.debug(f"Moved file {file_id} to folder {new_folder_id}")

    def rename_file(self, file_id: str, new_name: str) -> None:
        """Rename a file in Drive."""
        svc = self._get_service()
        svc.files().update(fileId=file_id, body={"name": new_name}).execute()
        log.debug(f"Renamed file {file_id} to {new_name}")

    def download_file(self, file_id: str) -> bytes:
        """Download a file from Drive and return its bytes."""
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import]

        svc = self._get_service()
        request = svc.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def list_folder(self, folder_id: str) -> list[dict[str, str]]:
        """
        List files in a Drive folder.

        Returns:
            List of dicts with 'id', 'name', 'mimeType', 'md5Checksum'.
        """
        svc = self._get_service()
        results = []
        page_token = None

        while True:
            kwargs: dict[str, Any] = {
                "q": f"'{folder_id}' in parents and trashed=false",
                "fields": "nextPageToken, files(id, name, mimeType, md5Checksum, size)",
                "pageSize": 1000,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            response = svc.files().list(**kwargs).execute()
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results

    def trash_file(self, file_id: str) -> None:
        """Soft delete — move to trash. Never hard-deletes."""
        svc = self._get_service()
        svc.files().update(fileId=file_id, body={"trashed": True}).execute()
        log.debug(f"Trashed file {file_id}")

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify_upload(self, file_id: str, expected_md5: str, filename: str) -> None:
        """Verify upload integrity using Drive's md5Checksum metadata field."""
        svc = self._get_service()
        try:
            meta = svc.files().get(fileId=file_id, fields="md5Checksum").execute()
            actual = meta.get("md5Checksum", "")
            if not actual:
                log.warning(f"Drive returned no md5Checksum for {filename}; skipping verification")
                return
            if actual != expected_md5:
                raise RuntimeError(
                    f"Upload verification FAILED for {filename}.\n"
                    f"Expected MD5: {expected_md5}\n"
                    f"Drive MD5:    {actual}\n"
                    "The file may be corrupt. Re-uploading is recommended."
                )
            log.debug(f"Upload verified: {filename} (md5={actual[:12]}...)")
        except RuntimeError:
            raise
        except Exception as exc:
            log.error(f"Upload verification error for {filename}: {exc}")
            raise


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
