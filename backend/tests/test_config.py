from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "groq"
    assert s.embedding_provider == "sentence-transformers"
    assert s.chunk_size == 800 and s.chunk_overlap == 120
    assert s.fusion_method == "weighted" and s.vector_weight == 0.7
    assert s.store_dir == s.data_dir / "store"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("CHUNK_SIZE", "500")
    monkeypatch.setenv("CHUNK_OVERLAP", "50")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"
    assert s.chunk_size == 500
    assert s.llm_api_key == "sk-test"
    assert s.resolved_llm_model == "gpt-4o-mini"
    assert s.llm_base_url is None


def test_provider_defaults_groq_and_together():
    g = Settings(_env_file=None, llm_provider="groq", groq_api_key="g")
    assert g.llm_base_url == "https://api.groq.com/openai/v1"
    assert g.llm_api_key == "g"
    t = Settings(_env_file=None, llm_provider="together", llm_model="custom/model")
    assert t.resolved_llm_model == "custom/model"
    assert "together" in t.llm_base_url


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chunk_size=100, chunk_overlap=100)


def test_invalid_provider_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="nope")


def test_cors_origins_comma_separated(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["http://a.com", "http://b.com"]


def test_max_upload_bytes():
    assert Settings(_env_file=None, max_upload_mb=2).max_upload_bytes == 2 * 1024 * 1024


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
