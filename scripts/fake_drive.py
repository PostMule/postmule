"""An in-memory stand-in for the Google Drive v3 API surface `google_drive.py` uses.

This is a TRANSPORT double, not a provider double. The real `DriveProvider` runs
unmodified on top of it, so the gate exercises the provider's actual code: the upload call,
the `md5Checksum` read-back, the parent add/remove of a move, the rename body, and the
soft-delete-only rule. Only the network is replaced.

Why it matters (app #113): the old gate filed through `LocalStorageProvider`, whose file id
is a filesystem path and which has no checksum concept at all, so the
execute -> MD5-verify path named in the architecture invariants was never executed by the
one test that claims to certify a release.

Integrity here is real, not simulated: `files().create` hashes the bytes it is actually
handed and `files().get` returns that hash, so `_verify_upload` compares a genuine MD5 of
genuine bytes. `corrupt_md5_for` flips that, which is how the gate proves it can FAIL when
Drive hands back a file that does not match what was sent.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_FOLDER_MIME = "application/vnd.google-apps.folder"


class FakeDriveError(RuntimeError):
    """Raised for operations the double refuses (a hard delete) or cannot serve."""


class _Request:
    """A pending API call. The real client returns one of these; work happens in execute()."""

    def __init__(self, fn):
        self._fn = fn

    def execute(self) -> Any:
        return self._fn()


class _Files:
    def __init__(self, drive: "FakeDriveService") -> None:
        self._d = drive

    def create(self, body=None, media_body=None, fields=None) -> _Request:
        return _Request(lambda: self._d._create(body or {}, media_body))

    def get(self, fileId=None, fields=None) -> _Request:  # noqa: N803 - Google's parameter name
        return _Request(lambda: self._d._get(fileId, fields))

    def update(self, fileId=None, addParents=None, removeParents=None,  # noqa: N803
               body=None, fields=None) -> _Request:
        return _Request(lambda: self._d._update(fileId, addParents, removeParents, body or {}))

    def list(self, q=None, fields=None, pageSize=None, pageToken=None) -> _Request:  # noqa: N803
        return _Request(lambda: self._d._list(q or ""))

    def delete(self, fileId=None) -> _Request:  # noqa: N803
        def _refuse():
            self._d.hard_delete_attempts.append(fileId)
            raise FakeDriveError(
                f"hard delete attempted on {fileId}. PostMule is soft-delete-only "
                "(max 0 auto-deletes ever) -- this call must never happen in a pipeline run."
            )
        return _Request(_refuse)


class FakeDriveService:
    """The `service` object `DriveProvider._get_service()` would return.

    Every stored file keeps its real bytes and their real MD5. Inspect `hard_delete_attempts`
    and `trashed_ids` after a run to assert the soft-delete invariant held.
    """

    def __init__(self) -> None:
        self.files_by_id: dict[str, dict[str, Any]] = {}
        self.hard_delete_attempts: list[str] = []
        self.trashed_ids: list[str] = []
        self.verified_md5_reads: list[str] = []
        self.corrupt_all_md5 = False
        self._corrupt: dict[str, str] = {}
        self._next_id = 1

    # --- test-facing controls -------------------------------------------------

    def corrupt_md5_for(self, file_id: str, wrong_md5: str = "0" * 32) -> None:
        """Make Drive report a checksum that does not match the stored bytes.

        The negative control for the integrity path: a gate that cannot fail here is not
        checking integrity at all. `corrupt_all_md5` is the same lever for a file whose id
        is only assigned mid-run, which is the case for anything the pipeline uploads.
        """
        self._corrupt[file_id] = wrong_md5

    def stored_bytes(self, file_id: str) -> bytes:
        return self.files_by_id[file_id]["content"]

    def files_in(self, folder_id: str) -> list[dict[str, Any]]:
        return [
            f for f in self.files_by_id.values()
            if folder_id in f["parents"] and not f["trashed"] and f["mimeType"] != _FOLDER_MIME
        ]

    # --- API surface ----------------------------------------------------------

    def files(self) -> _Files:
        return _Files(self)

    def about(self):
        class _About:
            def get(self, fields=None):
                return _Request(lambda: {"user": {"emailAddress": "e2e@example.invalid"}})
        return _About()

    # --- implementation -------------------------------------------------------

    def _create(self, body: dict[str, Any], media_body: Any) -> dict[str, Any]:
        file_id = f"fake-{self._next_id:04d}"
        self._next_id += 1
        content = b""
        if media_body is not None:
            # MediaFileUpload / MediaInMemoryUpload both expose size() + getbytes().
            size = media_body.size() or 0
            content = media_body.getbytes(0, size) if size else b""
        record = {
            "id": file_id,
            "name": body.get("name", ""),
            "mimeType": body.get("mimeType", "application/octet-stream"),
            "parents": list(body.get("parents") or []),
            "content": content,
            "md5Checksum": hashlib.md5(content, usedforsecurity=False).hexdigest(),
            "size": str(len(content)),
            "trashed": False,
        }
        self.files_by_id[file_id] = record
        return {"id": file_id, "name": record["name"], "size": record["size"]}

    def _get(self, file_id: str, fields: str | None) -> dict[str, Any]:
        record = self.files_by_id.get(file_id)
        if record is None:
            raise FakeDriveError(f"no such file: {file_id}")
        if fields and "md5Checksum" in fields:
            self.verified_md5_reads.append(file_id)
            if self.corrupt_all_md5:
                return {"md5Checksum": "0" * 32}
            return {"md5Checksum": self._corrupt.get(file_id, record["md5Checksum"])}
        return {k: v for k, v in record.items() if k != "content"}

    def _update(self, file_id: str, add_parents, remove_parents, body: dict[str, Any]):
        record = self.files_by_id.get(file_id)
        if record is None:
            raise FakeDriveError(f"no such file: {file_id}")
        if remove_parents:
            for parent in str(remove_parents).split(","):
                if parent in record["parents"]:
                    record["parents"].remove(parent)
        if add_parents:
            for parent in str(add_parents).split(","):
                if parent not in record["parents"]:
                    record["parents"].append(parent)
        if "name" in body:
            record["name"] = body["name"]
        if body.get("trashed"):
            record["trashed"] = True
            self.trashed_ids.append(file_id)
        return {"id": file_id, "parents": list(record["parents"])}

    def _list(self, query: str) -> dict[str, Any]:
        """Serve the two query shapes the provider builds: a folder lookup and a folder listing."""
        name = _match(r"name='([^']*)'", query)
        mime = _match(r"mimeType='([^']*)'", query)
        parent = _match(r"'([^']*)' in parents", query)

        matches = []
        for record in self.files_by_id.values():
            if record["trashed"]:
                continue
            if name is not None and record["name"] != name:
                continue
            if mime is not None and record["mimeType"] != mime:
                continue
            if parent is not None and parent not in record["parents"]:
                continue
            matches.append({
                "id": record["id"],
                "name": record["name"],
                "mimeType": record["mimeType"],
                "md5Checksum": record["md5Checksum"],
                "size": record["size"],
            })
        return {"files": matches}


def _match(pattern: str, text: str) -> str | None:
    found = re.search(pattern, text)
    return found.group(1) if found else None
