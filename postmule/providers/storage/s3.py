"""
Amazon S3 storage provider.

Uses boto3 with AWS access key credentials.

Config example:
    storage:
      providers:
        - service: s3
          enabled: true
          bucket: my-postmule-bucket
          region: us-east-1
          root_prefix: PostMule/

Notes:
  - File IDs are full S3 keys (e.g. "PostMule/Bills/2025-01-01_Alice_ATT_Bill.pdf").
  - Folder IDs are key prefixes (e.g. "PostMule/Bills/").
  - MD5 verification uses S3 ETag; multipart-upload ETags contain '-' and cannot be
    verified this way — a warning is logged and verification is skipped for those.
  - delete_file performs a hard delete (no soft-delete trash in S3).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger("postmule.storage.s3")

SERVICE_KEY = "s3"
DISPLAY_NAME = "Amazon S3"


class S3Provider:
    """
    Amazon S3 storage provider.

    Args:
        bucket:            S3 bucket name.
        region:            AWS region (e.g. 'us-east-1').
        access_key_id:     AWS access key ID.
        secret_access_key: AWS secret access key.
        root_prefix:       Top-level key prefix inside the bucket (default: 'PostMule/').
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        root_prefix: str = "PostMule/",
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.root_prefix = root_prefix.rstrip("/") + "/"
        self._s3 = None

    def _get_client(self):
        if self._s3 is None:
            try:
                import boto3  # type: ignore[import]
            except ImportError:
                raise RuntimeError("boto3 is not installed. Run: pip install boto3")
            self._s3 = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
            )
        return self._s3

    def health_check(self):
        """Return a HealthResult by probing the configured S3 bucket."""
        from postmule.providers import HealthResult
        try:
            self._get_client().head_bucket(Bucket=self.bucket)
            return HealthResult(
                ok=True,
                status="ok",
                message=f"S3 bucket '{self.bucket}' ({self.region}) accessible",
            )
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------

    def ensure_folder_structure(self, folders: dict) -> dict:
        """
        S3 has no real folders — a zero-byte .keep object is placed at each prefix
        to make the 'folder' visible in the AWS console.

        Args:
            folders: Dict of {key: folder_name} from config.

        Returns:
            Dict of {key: prefix_string}.
        """
        s3 = self._get_client()
        result: dict[str, str] = {"root": self.root_prefix}

        for key, name in folders.items():
            prefix = f"{self.root_prefix}{name}/"
            _ensure_placeholder(s3, self.bucket, prefix)
            result[key] = prefix
            log.debug(f"S3 prefix ready: {prefix}")

        system_prefix = f"{self.root_prefix}_System/"
        data_prefix = f"{system_prefix}data/"
        _ensure_placeholder(s3, self.bucket, system_prefix)
        _ensure_placeholder(s3, self.bucket, data_prefix)
        result["system"] = system_prefix
        result["data"] = data_prefix
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
        Upload a PDF to an S3 prefix.

        Args:
            local_path: Local path to the PDF.
            filename:   Name to use in S3.
            folder_id:  S3 prefix string (e.g. "PostMule/Bills/").
            verify:     If True, compare local MD5 against S3 ETag after upload.

        Returns:
            S3 key of the uploaded object (used as file_id).
        """
        key = f"{folder_id.rstrip('/')}/{filename}"
        s3 = self._get_client()
        local_md5 = _md5_file(local_path)

        with local_path.open("rb") as f:
            s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=f,
                ContentType="application/pdf",
            )
        log.info(f"Uploaded: {filename} -> s3://{self.bucket}/{key}")

        if verify:
            self._verify_upload(key, local_md5, filename)

        return key

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload arbitrary bytes to an S3 prefix; return the S3 key as file ID."""
        key = f"{folder_id.rstrip('/')}/{filename}"
        s3 = self._get_client()
        s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=mimetype,
        )
        log.info(f"Uploaded bytes: {filename} -> s3://{self.bucket}/{key}")
        return key

    def move_file(self, file_id: str, new_folder_id: str, old_folder_id: str) -> None:
        """Move a file between S3 prefixes via copy + delete."""
        s3 = self._get_client()
        filename = file_id.rsplit("/", 1)[-1]
        new_key = f"{new_folder_id.rstrip('/')}/{filename}"
        s3.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": file_id},
            Key=new_key,
        )
        s3.delete_object(Bucket=self.bucket, Key=file_id)
        log.debug(f"Moved S3 object: {file_id} -> {new_key}")

    def rename_file(self, file_id: str, new_name: str) -> None:
        """Rename an S3 object via copy + delete."""
        s3 = self._get_client()
        prefix = file_id.rsplit("/", 1)[0]
        new_key = f"{prefix}/{new_name}"
        s3.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": file_id},
            Key=new_key,
        )
        s3.delete_object(Bucket=self.bucket, Key=file_id)
        log.debug(f"Renamed S3 object: {file_id} -> {new_key}")

    def list_folder(self, folder_id: str) -> list[dict[str, str]]:
        """
        List objects directly inside an S3 prefix.

        Returns list of dicts with 'id' (S3 key), 'name', 'size'.
        """
        s3 = self._get_client()
        prefix = folder_id if folder_id.endswith("/") else f"{folder_id}/"
        results = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                name = key[len(prefix):]
                if name and name != ".keep":
                    results.append({"id": key, "name": name, "size": str(obj.get("Size", 0))})
        return results

    def delete_file(self, file_id: str) -> None:
        """Permanently delete an S3 object by key."""
        self._get_client().delete_object(Bucket=self.bucket, Key=file_id)
        log.info(f"Deleted S3 object: {file_id}")

    def download_file(self, file_id: str) -> bytes:
        """Download an S3 object by key and return raw bytes."""
        resp = self._get_client().get_object(Bucket=self.bucket, Key=file_id)
        return resp["Body"].read()

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify_upload(self, key: str, expected_md5: str, filename: str) -> None:
        """
        Verify upload integrity via S3 ETag.

        For single-part uploads (< 5 GB via put_object), ETag == MD5 hex digest.
        Multipart ETags contain '-' and use a different format — verification is
        skipped with a warning in that case.
        """
        s3 = self._get_client()
        try:
            meta = s3.head_object(Bucket=self.bucket, Key=key)
            etag = meta.get("ETag", "").strip('"')
            if "-" in etag:
                log.warning(
                    f"S3 multipart ETag for '{filename}'; MD5 verification skipped. "
                    "ETag format differs for multipart uploads."
                )
                return
            if etag != expected_md5:
                raise RuntimeError(
                    f"Upload verification FAILED for '{filename}'.\n"
                    f"Expected MD5: {expected_md5}\n"
                    f"S3 ETag:      {etag}\n"
                    "The file may be corrupt. Re-uploading is recommended."
                )
            log.debug(f"Upload verified: {filename} (md5={etag[:12]}...)")
        except RuntimeError:
            raise
        except Exception as exc:
            log.error(f"Upload verification error for '{filename}': {exc}")
            raise


def _ensure_placeholder(s3, bucket: str, prefix: str) -> None:
    """Place a zero-byte .keep object at a prefix if not already present."""
    placeholder = f"{prefix}.keep"
    try:
        s3.head_object(Bucket=bucket, Key=placeholder)
    except Exception:
        s3.put_object(Bucket=bucket, Key=placeholder, Body=b"")


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
