"""
Microsoft OneDrive storage provider via the Microsoft Graph API.

Uses an OAuth2 bearer token (same infrastructure as the Outlook email providers).

Config example:
    storage:
      providers:
        - service: onedrive
          enabled: true
          root_folder: PostMule

Notes:
  - File IDs are OneDrive item IDs returned by the Graph API.
  - Folder IDs are OneDrive item IDs.
  - Integrity verification uses SHA-1 (available from Graph API file.hashes.sha1Hash).
    The SHA-1 is computed locally and compared against the value Graph returns after upload.
  - delete_file performs a hard delete.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger("postmule.storage.onedrive")

SERVICE_KEY = "onedrive"
DISPLAY_NAME = "OneDrive"

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_UPLOAD_THRESHOLD = 4 * 1024 * 1024  # 4 MB — use simple PUT below this size


class OneDriveProvider:
    """
    Microsoft OneDrive storage provider via the Graph API.

    Args:
        access_token: OAuth2 bearer token.
        root_folder:  Top-level OneDrive folder name (default: 'PostMule').
    """

    def __init__(
        self,
        access_token: str,
        root_folder: str = "PostMule",
    ) -> None:
        self.access_token = access_token
        self.root_folder = root_folder
        self._folder_cache: dict[str, str] = {}

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, **params) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.get(f"{_GRAPH_BASE}{path}", headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.post(f"{_GRAPH_BASE}{path}", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, body: dict) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.patch(f"{_GRAPH_BASE}{path}", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _put_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }
        resp = requests.put(f"{_GRAPH_BASE}{path}", headers=headers, data=data, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> None:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.delete(f"{_GRAPH_BASE}{path}", headers=self._headers(), timeout=30)
        resp.raise_for_status()

    def health_check(self):
        """Return a HealthResult by calling /me/drive on the Graph API."""
        from postmule.providers import HealthResult
        try:
            data = self._get("/me/drive")
            quota = data.get("quota", {})
            used_gb = round(quota.get("used", 0) / 1e9, 2)
            return HealthResult(
                ok=True,
                status="ok",
                message=f"OneDrive connected ({used_gb} GB used)",
            )
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------

    def ensure_folder_structure(self, folders: dict) -> dict:
        """
        Create all required OneDrive folders under root_folder if they don't exist.

        Args:
            folders: Dict of {key: folder_name} from config.

        Returns:
            Dict of {key: item_id}.
        """
        root_id = self._get_or_create_folder(self.root_folder, parent_id=None)
        self._folder_cache["root"] = root_id
        result: dict[str, str] = {"root": root_id}

        for key, name in folders.items():
            folder_id = self._get_or_create_folder(name, parent_id=root_id)
            self._folder_cache[key] = folder_id
            result[key] = folder_id
            log.debug(f"OneDrive folder ready: {name} ({folder_id})")

        system_id = self._get_or_create_folder("_System", parent_id=root_id)
        data_id = self._get_or_create_folder("data", parent_id=system_id)
        result["system"] = system_id
        result["data"] = data_id
        return result

    def _get_or_create_folder(self, name: str, parent_id: str | None) -> str:
        """Return item ID of folder, creating it if needed."""
        if parent_id:
            path = f"/me/drive/items/{parent_id}/children"
        else:
            path = "/me/drive/root/children"

        # Search for existing folder
        try:
            data = self._get(path, **{"$filter": f"name eq '{name}' and folder ne null"})
            for item in data.get("value", []):
                if item.get("name") == name and "folder" in item:
                    return item["id"]
        except Exception:
            pass

        # Create folder
        body = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
        try:
            result = self._post(path, body)
            log.info(f"Created OneDrive folder: {name}")
            return result["id"]
        except Exception:
            # May already exist (race or filter miss) — try listing again
            data = self._get(path)
            for item in data.get("value", []):
                if item.get("name") == name and "folder" in item:
                    return item["id"]
            raise

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
        Upload a PDF to a OneDrive folder.

        Args:
            local_path: Local path to the PDF.
            filename:   Name to use in OneDrive.
            folder_id:  OneDrive item ID of the target folder.
            verify:     If True, compare local SHA-1 against Graph API sha1Hash.

        Returns:
            OneDrive item ID of the uploaded file (used as file_id).
        """
        data = local_path.read_bytes()
        local_sha1 = _sha1_bytes(data)

        result = self._put_bytes(
            f"/me/drive/items/{folder_id}:/{filename}:/content",
            data,
            content_type="application/pdf",
        )
        file_id = result["id"]
        log.info(f"Uploaded: {filename} -> OneDrive ({file_id})")

        if verify:
            self._verify_upload(file_id, local_sha1, filename)

        return file_id

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload arbitrary bytes to a OneDrive folder; return the item ID."""
        result = self._put_bytes(
            f"/me/drive/items/{folder_id}:/{filename}:/content",
            data,
            content_type=mimetype,
        )
        file_id = result["id"]
        log.info(f"Uploaded bytes: {filename} -> OneDrive ({file_id})")
        return file_id

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        """Move a file to a different OneDrive folder."""
        self._patch(
            f"/me/drive/items/{file_id}",
            {"parentReference": {"id": new_folder_id}},
        )
        log.debug(f"Moved OneDrive item {file_id} to folder {new_folder_id}")

    def rename_file(self, file_id: str, new_name: str) -> None:
        """Rename a OneDrive item in place."""
        self._patch(f"/me/drive/items/{file_id}", {"name": new_name})
        log.debug(f"Renamed OneDrive item {file_id} to '{new_name}'")

    def list_folder(self, folder_id: str) -> list[dict[str, str]]:
        """
        List files in a OneDrive folder.

        Returns list of dicts with 'id', 'name', 'size'.
        """
        results = []
        path = f"/me/drive/items/{folder_id}/children"
        params: dict = {"$select": "id,name,size,file"}

        while True:
            try:
                data = self._get(path, **params)
            except Exception as exc:
                log.error(f"OneDrive list_folder failed: {exc}")
                break

            for item in data.get("value", []):
                if "file" in item:
                    results.append({
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "size": str(item.get("size", 0)),
                    })

            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            path = next_link.replace(_GRAPH_BASE, "")
            params = {}

        return results

    def delete_file(self, file_id: str) -> None:
        """Permanently delete a OneDrive item by item ID."""
        self._delete(f"/me/drive/items/{file_id}")
        log.info(f"Deleted OneDrive item: {file_id}")

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify_upload(self, file_id: str, expected_sha1: str, filename: str) -> None:
        """Verify upload integrity using the SHA-1 hash from Graph API file metadata."""
        try:
            meta = self._get(f"/me/drive/items/{file_id}", **{"$select": "file"})
            hashes = meta.get("file", {}).get("hashes", {})
            actual = hashes.get("sha1Hash", "").lower()
            if not actual:
                log.warning(f"Graph API returned no sha1Hash for '{filename}'; skipping verification")
                return
            if actual != expected_sha1.lower():
                raise RuntimeError(
                    f"Upload verification FAILED for '{filename}'.\n"
                    f"Expected SHA-1: {expected_sha1}\n"
                    f"OneDrive SHA-1: {actual}\n"
                    "The file may be corrupt. Re-uploading is recommended."
                )
            log.debug(f"Upload verified: {filename} (sha1={actual[:12]}...)")
        except RuntimeError:
            raise
        except Exception as exc:
            log.error(f"Upload verification error for '{filename}': {exc}")
            raise


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()
