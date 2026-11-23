from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Isolated settings: fake providers, temp data dir, in-memory-friendly paths."""
    return Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        qdrant_path=tmp_path / "qdrant",
        llm_provider="fake",
        embedding_provider="fake",
        embedding_dim=64,
    )
