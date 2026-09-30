"""Embeddings. Interface: embed(texts, task) -> list[list[float]].

Provider is chosen by EMBEDDING_PROVIDER:
  vertex  VertexEmbedder: Vertex AI via google-genai (gemini-embedding-001, 768 dims). Needs Vertex Gen AI
          to be allowed on the project; blocked by some org policies (constraints/vertexai.allowedModels).
  local   LocalEmbedder: sentence-transformers running inside the backend, no Vertex, no org-policy dependency.
          Default model paraphrase-multilingual-MiniLM-L12-v2 (384 dims); set EMBEDDING_DIM to match.
  hash    HashEmbedder: deterministic hashed bag-of-words, no network. Tests and the `memory` store only.

Seed and live calls must use the same provider, model and dimension, otherwise the similarities are meaningless.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

log = logging.getLogger(__name__)

TASK_QUERY = "RETRIEVAL_QUERY"  # the problem of an incoming call
TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"  # the problem_text of a solution in the knowledge base


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str], task: str) -> list[list[float]]: ...


class VertexEmbedder:
    def __init__(self, project: str, region: str, model: str, dim: int):
        from google import genai

        self._client = genai.Client(vertexai=True, project=project, location=region)
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task, output_dimensionality=self.dim)
        out: list[list[float]] = []
        for text in texts:  # gemini-embedding-001 on Vertex takes one input per request
            resp = self._client.models.embed_content(model=self.model, contents=text, config=config)
            values = list(resp.embeddings[0].values)
            if len(values) != self.dim:
                raise RuntimeError(f"embedding has {len(values)} dims, EMBEDDING_DIM is {self.dim}")
            out.append(values)
        return out


class LocalEmbedder:
    """sentence-transformers, loaded once. Multilingual (NL/FR/EN). Embeddings are L2-normalised so the
    cosine distance stored in Firestore is comparable across calls and solutions."""

    def __init__(self, model: str, dim: int):
        from sentence_transformers import SentenceTransformer

        log.info("loading local embedding model %s (first run downloads it)", model)
        self._model = SentenceTransformer(model)
        self.dim = dim
        self._name = model
        got = self._model.get_sentence_embedding_dimension()
        if got != dim:
            raise RuntimeError(f"model {model} has {got} dims, EMBEDDING_DIM is {dim}; set EMBEDDING_DIM={got}")

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        # this model is symmetric, so query and document use the same encoding; task is ignored
        vectors = self._model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [[float(x) for x in row] for row in vectors]


class HashEmbedder:
    """Not semantic: shared words give similarity. Enough to test the flow without GCP."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in re.findall(r"\w{3,}", text.lower()):
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def resolve_project(configured: str) -> str:
    if configured:
        return configured
    import google.auth

    _, project = google.auth.default()
    if not project:
        raise RuntimeError("GCP_PROJECT is not set and could not be derived from the credentials")
    return project


def make_embedder(settings) -> Embedder:
    provider = (settings.embedding_provider or "vertex").lower()
    if provider == "hash" or settings.store_backend == "memory":
        return HashEmbedder(settings.embedding_dim)
    if provider == "local":
        log.info("using local embeddings %s (%d dims)", settings.embedding_model, settings.embedding_dim)
        return LocalEmbedder(settings.embedding_model, settings.embedding_dim)
    project = resolve_project(settings.gcp_project)
    log.info("using Vertex embeddings %s in %s", settings.embedding_model, settings.gcp_region)
    return VertexEmbedder(project, settings.gcp_region, settings.embedding_model, settings.embedding_dim)
