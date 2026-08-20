from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Protocol


class ObjectStorageService(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> tuple[bytes, str]: ...

    def runtime_status(self) -> dict[str, object]: ...


class ObjectNotFoundError(FileNotFoundError):
    """Raised when `key` does not exist in the configured object storage."""


class LocalDiskObjectStorage:
    """Default provider: writes under `data/uploads/`.

    Zero-config fallback used when S3/MinIO is not configured or not
    reachable at startup (ENVIRONMENT.md Object Storage). Keeps local
    dev/demo working with no external dependency, matching the Noop/
    dev-bypass convention used by the other optional integrations.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Object key escapes the configured storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> tuple[bytes, str]:
        path = self._resolve(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return path.read_bytes(), content_type

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "LOCAL_DISK",
            "provider": "local",
            "bucket": str(self.root),
            "configured": True,
        }


class S3ObjectStorage:
    """S3-compatible provider shared by MinIO (dev/demo) and AWS S3
    (production) — one boto3 client; only `endpoint` differs.

    ENVIRONMENT.md: `OBJECT_STORAGE_PROVIDER=minio` for local dev/demo,
    `s3` for AWS S3 or another S3-compatible service. Switching between the
    two in production is an environment-variable change only, never a code
    change, as long as the caller keeps using this same class.
    """

    def __init__(
        self,
        *,
        provider: str,
        bucket: str,
        endpoint: str | None,
        access_key: str,
        secret_key: str,
        region: str | None,
    ) -> None:
        import boto3
        from botocore.client import Config

        self.provider = provider
        self.bucket = bucket
        self.endpoint = endpoint
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region or "us-east-1",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"} if endpoint else {},
            ),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            if self.provider != "minio":
                # AWS S3 buckets are provisioned as infrastructure (Terraform/
                # console), not auto-created by the app; a missing bucket on
                # "s3" surfaces as a clear error on first read/write instead.
                return
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> tuple[bytes, str]:
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            raise ObjectNotFoundError(key) from error
        return response["Body"].read(), response.get("ContentType") or "application/octet-stream"

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "OBJECT_STORAGE",
            "provider": self.provider,
            "bucket": self.bucket,
            "endpoint": self.endpoint or "aws-default",
            "configured": True,
        }


__all__: tuple[str, ...] = (
    "ObjectStorageService",
    "ObjectNotFoundError",
    "LocalDiskObjectStorage",
    "S3ObjectStorage",
)
