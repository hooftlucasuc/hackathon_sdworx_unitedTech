"""Raw source files in Cloud Storage (immutable originals)."""

from __future__ import annotations

import logging
from typing import Optional, Protocol

log = logging.getLogger(__name__)


class RawStore(Protocol):
    def put(self, path: str, data: bytes, content_type: Optional[str] = None) -> str: ...


class GcsStore:
    def __init__(self, bucket_name: str, project: Optional[str] = None):
        from google.cloud import storage

        self._client = storage.Client(project=project or None)
        self._bucket = self._client.bucket(bucket_name)
        self._name = bucket_name

    def put(self, path: str, data: bytes, content_type: Optional[str] = None) -> str:
        blob = self._bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type or "application/octet-stream")
        uri = f"gs://{self._name}/{path}"
        log.info("stored raw file %s (%d bytes)", uri, len(data))
        return uri


class NullRawStore:
    """Memory backend: nothing is stored; returns a pseudo-uri."""

    def put(self, path: str, data: bytes, content_type: Optional[str] = None) -> str:
        return f"memory://{path}"


def make_raw_store(settings) -> RawStore:
    if settings.store_backend == "memory":
        return NullRawStore()
    return GcsStore(settings.bucket_name, settings.gcp_project)
