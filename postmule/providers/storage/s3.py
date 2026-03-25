"""
Amazon S3 storage provider — stub (not yet implemented).

Implementation will use boto3 to store PDFs and JSON data files in an S3 bucket.

Config example:
    storage:
      providers:
        - service: s3
          enabled: true
          bucket: my-postmule-bucket
          region: us-east-1
          root_prefix: PostMule/
"""

from __future__ import annotations

from pathlib import Path

SERVICE_KEY = "s3"
DISPLAY_NAME = "Amazon S3"


class S3Provider:
    """
    Amazon S3 storage provider.

    Not yet implemented. Configure service: s3 in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Amazon S3 provider is not yet implemented. "
            "Use service: google_drive in config.yaml for now."
        )

    def upload_pdf(self, local_path: Path, filename: str, folder_id: str, verify: bool = True) -> str:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")

    def rename_file(self, file_id: str, new_name: str) -> None:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")

    def list_folder(self, folder_id: str) -> list:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")

    def ensure_folder_structure(self, folders: dict) -> dict:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")

    def upload_bytes(self, data: bytes, filename: str, folder_id: str, mimetype: str = "application/octet-stream") -> str:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")

    def delete_file(self, file_id: str) -> None:
        raise NotImplementedError("Amazon S3 provider is not yet implemented.")
