"""Private object storage. Files are only reachable through short-lived signed URLs."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import httpx
import jwt

from app.core.config import ConfigurationError, get_settings


class StorageError(RuntimeError):
    pass


@dataclass
class SignedUpload:
    url: str
    method: str
    headers: dict[str, str]


class StorageProvider(ABC):
    @abstractmethod
    def signed_upload(self, path: str, content_type: str) -> SignedUpload: ...
    @abstractmethod
    def signed_download(self, path: str, ttl: int | None = None) -> str: ...
    @abstractmethod
    def read(self, path: str) -> bytes: ...
    @abstractmethod
    def write(self, path: str, data: bytes, content_type: str) -> None: ...
    @abstractmethod
    def delete(self, path: str) -> None: ...


class SupabaseStorage(StorageProvider):
    def __init__(self):
        s = get_settings()
        if not s.supabase_url or not s.supabase_service_role_key:
            raise ConfigurationError("Storage needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. See docs/DEPLOYMENT.md.")
        self.base, self.bucket, self.ttl = s.supabase_url.rstrip("/") + "/storage/v1", s.supabase_storage_bucket, s.signed_url_ttl_seconds
        self.http = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {s.supabase_service_role_key}",
                                                       "apikey": s.supabase_service_role_key})

    def _obj(self, path: str) -> str:
        return f"{self.bucket}/{quote(path)}"

    def _check(self, r: httpx.Response, what: str) -> httpx.Response:
        if r.status_code >= 300:
            raise StorageError(f"Supabase Storage {what} failed: HTTP {r.status_code}")
        return r

    def signed_upload(self, path: str, content_type: str) -> SignedUpload:
        r = self._check(self.http.post(f"{self.base}/object/upload/sign/{self._obj(path)}"), "signed upload")
        return SignedUpload(url=f"{self.base}{r.json()['url']}", method="PUT", headers={"Content-Type": content_type, "x-upsert": "true"})

    def signed_download(self, path: str, ttl: int | None = None) -> str:
        r = self._check(self.http.post(f"{self.base}/object/sign/{self._obj(path)}", json={"expiresIn": ttl or self.ttl}), "signed download")
        return f"{self.base}{r.json()['signedURL']}"

    def read(self, path: str) -> bytes:
        return self._check(self.http.get(f"{self.base}/object/{self._obj(path)}"), "read").content

    def write(self, path: str, data: bytes, content_type: str) -> None:
        self._check(self.http.post(f"{self.base}/object/{self._obj(path)}", content=data,
                                   headers={"Content-Type": content_type, "x-upsert": "true"}), "write")

    def delete(self, path: str) -> None:
        self._check(self.http.request("DELETE", f"{self.base}/object/{self.bucket}", json={"prefixes": [path]}), "delete")


class LocalStorage(StorageProvider):
    """Development and CI backend with the same signed-URL contract as Supabase."""

    def __init__(self):
        s = get_settings()
        if s.is_production:
            raise ConfigurationError("STORAGE_PROVIDER=local is not allowed in production")
        self.root, self.api, self.ttl = Path(s.local_storage_dir).resolve(), s.public_api_url.rstrip("/"), s.signed_url_ttl_seconds
        self.secret = s.signing_secret()

    def _full(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if not p.is_relative_to(self.root):
            raise StorageError("Invalid path")
        return p

    def _token(self, path: str, op: str, ttl: int) -> str:
        return jwt.encode({"p": path, "op": op, "exp": int(time.time()) + ttl}, self.secret, algorithm="HS256")

    def verify(self, token: str, op: str) -> str:
        data = jwt.decode(token, self.secret, algorithms=["HS256"])
        if data["op"] != op:
            raise StorageError("Wrong token type")
        return data["p"]

    def signed_upload(self, path: str, content_type: str) -> SignedUpload:
        return SignedUpload(f"{self.api}/api/v1/local-storage/{self._token(path, 'put', self.ttl)}", "PUT", {"Content-Type": content_type})

    def signed_download(self, path: str, ttl: int | None = None) -> str:
        return f"{self.api}/api/v1/local-storage/{self._token(path, 'get', ttl or self.ttl)}"

    def read(self, path: str) -> bytes:
        p = self._full(path)
        if not p.exists():
            raise StorageError("File not found in storage")
        return p.read_bytes()

    def write(self, path: str, data: bytes, content_type: str) -> None:
        p = self._full(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def delete(self, path: str) -> None:
        self._full(path).unlink(missing_ok=True)


@lru_cache
def get_storage() -> StorageProvider:
    kind = get_settings().storage_provider
    if kind == "supabase":
        return SupabaseStorage()
    if kind == "local":
        return LocalStorage()
    raise ConfigurationError(f"Unknown STORAGE_PROVIDER '{kind}'")
