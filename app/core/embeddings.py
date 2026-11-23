"""Embedding providers behind a single small interface."""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.text import stem_token, tokenize

logger = get_logger(__name__)


class EmbeddingError(RuntimeError):
    """Embedding backend failed."""


@runtime_checkable
class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Deterministic hashed bag-of-words embedder for tests and offline development.

    Similarity is lexical (shared tokens), optionally made "semantic" by passing `synonyms`,
    a mapping of word -> canonical concept so that paraphrases land in the same buckets.
    """

    def __init__(self, dim: int = 256, synonyms: dict[str, str] | None = None) -> None:
        self._dim = dim
        # tokens are stemmed by `tokenize`, so stem the mapping the same way
        self._synonyms = {stem_token(k.lower()): stem_token(v.lower()) for k, v in (synonyms or {}).items()}

    @property
    def dim(self) -> int:
        return self._dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for tok in tokenize(text):
            tok = self._synonyms.get(tok, tok)
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)  # noqa: S324 - not security
            vec[h % self._dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            vec[0] = 1.0
            return vec
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class SentenceTransformerEmbedder:
    """Local embeddings via sentence-transformers (model is loaded lazily on first use)."""

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = None
        self._dim: int | None = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            get_dim = getattr(self._model, "get_embedding_dimension", None) or (
                self._model.get_sentence_embedding_dimension
            )
            self._dim = int(get_dim())
        return self._model

    @property
    def dim(self) -> int:
        self._load()
        assert self._dim is not None
        return self._dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vecs = self._load().encode(
                texts, batch_size=self._batch_size, normalize_embeddings=True, show_progress_bar=False
            )
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"sentence-transformers failed: {exc}") from exc
        return [v.tolist() for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OpenAIEmbedder:
    """OpenAI-compatible /embeddings endpoint over httpx (no extra SDK dependency)."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        batch_size: int = 96,
    ) -> None:
        if not api_key:
            raise EmbeddingError("OPENAI_API_KEY is required for the OpenAI embedding provider")
        self._api_key, self._model, self._dim = api_key, model, dim
        self._base_url, self._timeout, self._batch = base_url.rstrip("/"), timeout, batch_size

    @property
    def dim(self) -> int:
        return self._dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            batch = texts[i : i + self._batch]
            payload: dict = {"model": self._model, "input": batch}
            if self._model.startswith("text-embedding-3"):
                payload["dimensions"] = self._dim  # keep vector size == configured collection size
            try:
                resp = httpx.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise EmbeddingError(f"OpenAI embeddings failed: {exc}") from exc
            out.extend(d["embedding"] for d in data)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider
    if provider == "fake":
        return FakeEmbedder(dim=settings.embedding_dim)
    if provider == "openai":
        model = settings.embedding_model
        if model.startswith("sentence-transformers/"):  # default left untouched -> sensible OpenAI model
            model = "text-embedding-3-small"
        return OpenAIEmbedder(settings.openai_api_key, model=model, dim=settings.embedding_dim)
    return SentenceTransformerEmbedder(settings.embedding_model)
