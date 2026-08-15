import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings


class StorageBackend(ABC):
    """The application only ever talks to this interface — swapping local disk for S3/Azure
    Blob/GCS in production is a new class here, nothing else changes. Ported verbatim from
    SchoolAssist's app/core/storage.py (zero SchoolAssist-specific logic) as Phase 1's first
    real file-upload caller (AssetDocument)."""

    @abstractmethod
    async def save(self, *, storage_key: str, content: bytes) -> None: ...

    @abstractmethod
    async def read(self, *, storage_key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, *, storage_key: str) -> None: ...


class LocalStorageBackend(StorageBackend):
    """Dev/Basic-tier default — writes under a configured root directory (a Docker volume
    in production), keyed by a server-generated path so a client-supplied filename can never
    escape it (no path traversal via `../`)."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.file_storage_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        return self.root / storage_key

    async def save(self, *, storage_key: str, content: bytes) -> None:
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def read(self, *, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    async def delete(self, *, storage_key: str) -> None:
        path = self._resolve(storage_key)
        if path.exists():
            path.unlink()


def new_storage_key(tenant_id: uuid.UUID, filename: str) -> str:
    """Tenant-prefixed, server-generated — never derived from client input directly."""
    suffix = Path(filename).suffix[:20]
    return f"{tenant_id}/{uuid.uuid4()}{suffix}"


_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = LocalStorageBackend()
    return _backend
