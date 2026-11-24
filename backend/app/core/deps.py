"""Dependency-injection providers for FastAPI.

Routes depend on these callables (never on module-level singletons), so tests can swap
any of them with `app.dependency_overrides[...]`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
