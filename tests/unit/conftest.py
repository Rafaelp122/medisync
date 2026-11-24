"""Unit test profile isolation ensuring in-memory adapters without Docker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from src.core.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Generator

_RAW_SETTINGS_TEST_FILES = frozenset({"test_config.py", "test_config_profiles.py"})


@pytest.fixture(autouse=True)
def _use_test_settings_profile(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Activate TestSettings (in-memory backends) across unit tests."""
    if request.path.name in _RAW_SETTINGS_TEST_FILES:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
