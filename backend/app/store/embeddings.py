"""Embeddings. One function on the interface: embed(texts, task) -> list[list[float]].

VertexEmbedder: Vertex AI text embeddings in GCP_REGION (multilingual; NL/FR/EN/DE in one index).
HashEmbedder:   deterministic hashed bag-of-words. Only for tests and the `memory` store backend.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

log = logging.getLogger(__name__)

TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str], task: str) -> list[list[float]]: ...


class VertexEmbedder:
    def __init__(self, project: str, region: str, model: str, dim: int):
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        vertexai.init(project=project, location=region)
        self._model = TextEmbeddingModel.from_pretrained(model)
        self._model_name = model
        self.dim = dim
        # gemini-embedding-001 accepts one instance per request; the older models accept up to 250.
        self._batch = 1 if model.startswith("gemini-embedding") else 100
        self._supports_dim = model.startswith("gemini-embedding") or model.startswith("text-embedding-004")

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        from vertexai.language_models import TextEmbeddingInput

        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch):
            batch = [TextEmbeddingInput(t, task) for t in texts[start : start + self._batch]]
            kwargs = {"output_dimensionality": self.dim} if self._supports_dim else {}
            result = self._model.get_embeddings(batch, **kwargs)
            out.extend([list(e.values) for e in result])
        if out and len(out[0]) != self.dim:
            raise RuntimeError(f"embedding dim {len(out[0])} != EMBEDDING_DIM {self.dim}; fix .env or the index")
        log.debug("embedded %d texts with %s (%s)", len(texts), self._model_name, task)
        return out


class HashEmbedder:
    """Deterministic, dependency-free embedding for tests and offline dev. Not semantic."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = re.findall(r"\w+", text.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 - not security
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def make_embedder(settings) -> Embedder:
    if settings.store_backend == "memory":
        return HashEmbedder(settings.embedding_dim)
    return VertexEmbedder(settings.gcp_project, settings.gcp_region, settings.embedding_model, settings.embedding_dim)
