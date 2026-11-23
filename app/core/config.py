"""Central configuration, loaded from environment variables / `.env`."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProvider = Literal["groq", "openai", "together", "fake"]
EmbeddingProvider = Literal["sentence-transformers", "openai", "fake"]
FusionMethod = Literal["rrf", "weighted"]
EvalBackend = Literal["custom", "ragas"]

# provider -> (base_url, default_model)
LLM_PROVIDER_DEFAULTS: dict[str, tuple[str | None, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openai": (None, "gpt-4o-mini"),
    "together": ("https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "fake": (None, "fake-llm"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application ---
    app_name: str = "Enterprise Knowledge Agent"
    app_version: str = "0.1.0"
    app_env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("data")
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # --- LLM ---
    llm_provider: LLMProvider = "groq"
    llm_model: str = ""
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    groq_api_key: str = ""
    openai_api_key: str = ""
    together_api_key: str = ""

    # --- embeddings ---
    embedding_provider: EmbeddingProvider = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = Field(default=384, gt=0)

    # --- vector DB ---
    qdrant_url: str = ""
    qdrant_path: Path = Path("data/qdrant")
    qdrant_collection: str = "eka_chunks"

    # --- ingestion ---
    chunk_size: int = Field(default=800, gt=0)
    chunk_overlap: int = Field(default=120, ge=0)
    max_upload_mb: int = Field(default=25, gt=0)

    # --- retrieval ---
    retrieval_top_k: int = Field(default=5, gt=0, le=50)
    fusion_method: FusionMethod = "weighted"
    rrf_k: int = Field(default=60, gt=0)
    vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)

    # --- agents ---
    max_retrieval_loops: int = Field(default=2, ge=0, le=5)
    max_history_turns: int = Field(default=6, ge=0, le=50)

    # --- evaluation ---
    eval_backend: EvalBackend = "custom"
    eval_after_query: bool = False
    eval_concurrency: int = Field(default=2, ge=1, le=16)
    eval_questions_path: Path = Path("data/eval/questions.json")
    sample_docs_dir: Path = Path("data/sample_docs")

    # --- frontend ---
    backend_url: str = "http://localhost:8000"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _validate_chunking(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    # --- derived values ---
    @property
    def store_dir(self) -> Path:
        return self.data_dir / "store"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def resolved_llm_model(self) -> str:
        return self.llm_model or LLM_PROVIDER_DEFAULTS[self.llm_provider][1]

    @property
    def llm_base_url(self) -> str | None:
        return LLM_PROVIDER_DEFAULTS[self.llm_provider][0]

    @property
    def llm_api_key(self) -> str:
        return {
            "groq": self.groq_api_key,
            "openai": self.openai_api_key,
            "together": self.together_api_key,
            "fake": "fake",
        }[self.llm_provider]


@lru_cache
def get_settings() -> Settings:
    return Settings()
