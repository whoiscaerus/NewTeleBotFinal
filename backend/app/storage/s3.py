"""
PR-057: Storage Backend

Abstraction layer for file storage (S3 or local filesystem).
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    async def save_file(self, key: str, content: bytes) -> str:
        """Save file and return access URL."""
        pass

    @abstractmethod
    async def get_file(self, key: str) -> bytes:
        """Retrieve file content."""
        pass

    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """Delete file."""
        pass

    @abstractmethod
    async def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for temporary access."""
        pass


class LocalFileSystemStorage(StorageBackend):
    """Local filesystem storage backend.

    Stores files in a local directory. Useful for development/testing.
    """

    def __init__(self, base_path: str = "./storage/exports"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
        logger.info(f"LocalFileSystemStorage initialized at {base_path}")

    async def save_file(self, key: str, content: bytes) -> str:
        """Save file to local filesystem."""
        file_path = os.path.join(self.base_path, key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved file: {file_path}")
        return f"file://{file_path}"

    async def get_file(self, key: str) -> bytes:
        """Retrieve file from local filesystem."""
        file_path = os.path.join(self.base_path, key)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {key}")

        with open(file_path, "rb") as f:
            return f.read()

    async def delete_file(self, key: str) -> bool:
        """Delete file from local filesystem."""
        file_path = os.path.join(self.base_path, key)

        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
            return True
        return False

    async def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate local file URL (not truly presigned)."""
        # For local storage, return direct path
        # In production with HTTP server, this would be signed
        return f"/storage/{key}"


class S3Storage(StorageBackend):
    """AWS S3 storage backend (stub implementation).

    For production use, install boto3 and implement full S3 integration.
    """

    def __init__(
        self,
        bucket_name: str,
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        self.bucket_name = bucket_name
        self.region = region
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv(
            "AWS_SECRET_ACCESS_KEY"
        )

        logger.info(f"S3Storage initialized for bucket {bucket_name} in {region}")
        logger.warning("S3Storage is a stub. Install boto3 for full implementation.")

    async def save_file(self, key: str, content: bytes) -> str:
        """Save file to S3 (stub)."""
        # TODO: Implement with boto3
        # import boto3
        # s3_client = boto3.client('s3', region_name=self.region)
        # s3_client.put_object(Bucket=self.bucket_name, Key=key, Body=content)
        raise NotImplementedError(
            "S3Storage requires boto3. Use LocalFileSystemStorage for now."
        )

    async def get_file(self, key: str) -> bytes:
        """Retrieve file from S3 (stub)."""
        raise NotImplementedError(
            "S3Storage requires boto3. Use LocalFileSystemStorage for now."
        )

    async def delete_file(self, key: str) -> bool:
        """Delete file from S3 (stub)."""
        raise NotImplementedError(
            "S3Storage requires boto3. Use LocalFileSystemStorage for now."
        )

    async def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate presigned S3 URL (stub)."""
        # TODO: Implement with boto3
        # import boto3
        # s3_client = boto3.client('s3', region_name=self.region)
        # url = s3_client.generate_presigned_url(
        #     'get_object',
        #     Params={'Bucket': self.bucket_name, 'Key': key},
        #     ExpiresIn=expires_in
        # )
        # return url
        raise NotImplementedError(
            "S3Storage requires boto3. Use LocalFileSystemStorage for now."
        )


def get_storage_backend() -> StorageBackend:
    """Factory function to get configured storage backend.

    Reads STORAGE_BACKEND env var:
    - 'local' (default): LocalFileSystemStorage
    - 's3': S3Storage (requires boto3)
    """
    backend_type = os.getenv("STORAGE_BACKEND", "local").lower()

    if backend_type == "s3":
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            raise ValueError(
                "S3_BUCKET_NAME environment variable required for S3 storage"
            )
        return S3Storage(bucket_name=bucket_name)
    else:
        base_path = os.getenv("STORAGE_LOCAL_PATH", "./storage/exports")
        return LocalFileSystemStorage(base_path=base_path)
