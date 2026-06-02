import io

import boto3
from botocore.client import Config

from app.core.config import get_settings
from app.storage.base import StorageBackend


class S3StorageBackend(StorageBackend):
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
            config=Config(signature_version="s3v4"),
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self.client.upload_fileobj(io.BytesIO(data), self.bucket, key, ExtraArgs={"ContentType": content_type})
        return key

    async def download(self, key: str) -> bytes:
        buffer = io.BytesIO()
        self.client.download_fileobj(self.bucket, key, buffer)
        return buffer.getvalue()

    async def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def get_url(self, key: str) -> str:
        settings = get_settings()
        return f"{settings.S3_ENDPOINT}/{self.bucket}/{key}"
