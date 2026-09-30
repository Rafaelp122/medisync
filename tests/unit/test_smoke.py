"""Smoke test suite to validate test execution environment."""

from src import __file__ as src_init_file


def test_sync_environment() -> None:
    """Validate synchronous test runner and package discovery."""
    assert src_init_file is not None


async def test_async_environment(sample_async_resource: str) -> None:
    """Validate asynchronous test execution with pytest-asyncio."""
    assert sample_async_resource == "ready"
