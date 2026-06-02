from __future__ import annotations

from typing import Optional

from app.core.config import get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.s3 import S3StorageBackend

_storage: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.STORAGE_BACKEND == "s3":
            _storage = S3StorageBackend()
        else:
            _storage = LocalStorageBackend()
    return _storage
