"""
OneDrive storage provider — stub (not yet implemented).

Implementation will use the Microsoft Graph API with OAuth2.

Config example:
    storage:
      providers:
        - service: onedrive
          enabled: true
          root_folder: PostMule
"""

from __future__ import annotations

from pathlib import Path

SERVICE_KEY = "onedrive"
DISPLAY_NAME = "OneDrive"


class OneDriveProvider:
    """
    Microsoft OneDrive storage provider.

    Not yet implemented. Configure service: onedrive in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "OneDrive provider is not yet implemented. "
            "Use service: google_drive in config.yaml for now."
        )

    def upload_pdf(self, local_path: Path, filename: str, folder_id: str, verify: bool = True) -> str:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def rename_file(self, file_id: str, new_name: str) -> None:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def list_folder(self, folder_id: str) -> list:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def ensure_folder_structure(self, folders: dict) -> dict:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def upload_bytes(self, data: bytes, filename: str, folder_id: str, mimetype: str = "application/octet-stream") -> str:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def delete_file(self, file_id: str) -> None:
        raise NotImplementedError("OneDrive provider is not yet implemented.")

    def health_check(self):
        raise NotImplementedError("OneDrive provider is not yet implemented.")
