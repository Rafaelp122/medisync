"""Unit tests for lazy database engine initialization and core lean pruning."""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest
import src.core.database as db_mod
import src.core.valkey as valkey_mod
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def test_importing_core_database_does_not_create_engine_eagerly() -> None:
    """Importing Base and DbSessionDep must not create an AsyncEngine at import time."""
    code = (
        "import src.core.database as db; "
        "from src.core.database import Base, DbSessionDep; "
        "assert db._engine is None; "
        "assert db._session_factory is None"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.asyncio
async def test_lazy_get_engine_session_factory_and_dispose() -> None:
    """get_engine and get_session_factory lazily instantiate singletons and dispose."""
    await db_mod.dispose_engine()
    # Disposing again before any engine is created must remain a safe no-op
    await db_mod.dispose_engine()

    engine1 = db_mod.get_engine()
    engine2 = db_mod.get_engine()
    assert isinstance(engine1, AsyncEngine)
    assert engine1 is engine2

    factory1 = db_mod.get_session_factory()
    factory2 = db_mod.get_session_factory()
    assert isinstance(factory1, async_sessionmaker)
    assert factory1 is factory2

    await db_mod.dispose_engine()
    engine3 = db_mod.get_engine()
    assert engine3 is not engine1
    await db_mod.dispose_engine()


def test_core_valkey_exposes_valkey_dep_and_removed_legacy_dependencies() -> None:
    """ValkeyDep lives in src.core.valkey; core.dependencies is removed."""
    assert hasattr(valkey_mod, "ValkeyDep")
    assert not hasattr(valkey_mod, "get_arq_pool_client")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.core.dependencies")
