"""Lua script manager for atomic Valkey operations with caching and auto-healing."""

import hashlib
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import NoScriptError, ResponseError


class LuaScriptError(Exception):
    """Base exception for Lua script loading and execution errors."""

    pass


class LuaScriptNotFoundError(LuaScriptError):
    """Raised when a requested Lua script is not registered or found on disk."""

    pass


class LuaScriptManager:
    """Manages loading, SHA1 caching, preloading, and resilient execution of scripts."""

    def __init__(self, scripts_dir: Path | str | None = None) -> None:
        self._scripts_dir: Path = (
            Path(scripts_dir) if scripts_dir else Path(__file__).parent / "lua"
        )
        self._scripts: dict[str, str] = {}
        self._sha_cache: dict[str, str] = {}
        self._discover_and_load_scripts()

    def _discover_and_load_scripts(self) -> None:
        """Scan the scripts directory and register all .lua files."""
        if not self._scripts_dir.exists() or not self._scripts_dir.is_dir():
            return

        for file_path in self._scripts_dir.glob("*.lua"):
            script_name = file_path.stem
            self.load_script_from_file(file_path, script_name)

    def load_script_from_file(
        self,
        path: Path | str,
        script_name: str | None = None,
    ) -> str:
        """Read Lua script from file, register it, compute and return its SHA1."""
        file_path = Path(path)
        if not file_path.exists():
            raise LuaScriptNotFoundError(f"Lua script file not found: {file_path}")

        name = script_name or file_path.stem
        script_content = file_path.read_text(encoding="utf-8")
        return self.load_script_from_string(name, script_content)

    def load_script_from_string(self, script_name: str, script_content: str) -> str:
        """Register a Lua script string, compute its SHA1, and cache both."""
        sha = hashlib.sha1(script_content.encode("utf-8")).hexdigest()  # noqa: S324
        self._scripts[script_name] = script_content
        self._sha_cache[script_name] = sha
        return sha

    def get_script(self, script_name: str) -> str:
        """Retrieve the raw source of a registered script."""
        if script_name not in self._scripts:
            raise LuaScriptNotFoundError(
                f"Lua script '{script_name}' is not registered in LuaScriptManager."
            )
        return self._scripts[script_name]

    def get_sha(self, script_name: str) -> str | None:
        """Retrieve the cached SHA1 for a registered script."""
        return self._sha_cache.get(script_name)

    @property
    def registered_scripts(self) -> list[str]:
        """List all currently registered script names."""
        return list(self._scripts.keys())

    async def preload_scripts(self, client: Redis) -> dict[str, str]:
        """Preload all registered Lua scripts into Valkey via SCRIPT LOAD."""
        loaded_shas: dict[str, str] = {}
        for script_name, script_content in self._scripts.items():
            loaded_sha = await client.script_load(script_content)  # pyright: ignore[reportUnknownMemberType]
            sha_str = str(loaded_sha)
            self._sha_cache[script_name] = sha_str
            loaded_shas[script_name] = sha_str
        return loaded_shas

    async def execute_script(
        self,
        client: Redis,
        script_name: str,
        keys: Sequence[str] = (),
        args: Sequence[Any] = (),
    ) -> Any:
        """Execute Lua script using EVALSHA with automatic healing on NOSCRIPT."""
        script_content = self.get_script(script_name)
        sha = self._sha_cache.get(script_name)
        if not sha:
            sha = hashlib.sha1(script_content.encode("utf-8")).hexdigest()  # noqa: S324
            self._sha_cache[script_name] = sha

        numkeys = len(keys)
        keys_and_args: list[Any] = list(keys) + list(args)

        try:
            return await client.evalsha(sha, numkeys, *keys_and_args)  # pyright: ignore[reportUnknownMemberType]
        except (NoScriptError, ResponseError) as exc:
            # Self-healing: if Valkey flushed script cache (SCRIPT FLUSH / restart)
            if isinstance(exc, NoScriptError) or "NOSCRIPT" in str(exc):
                # Reload script on the fly
                reloaded_sha = await client.script_load(script_content)  # pyright: ignore[reportUnknownMemberType]
                sha = str(reloaded_sha)
                self._sha_cache[script_name] = sha
                try:
                    return await client.evalsha(sha, numkeys, *keys_and_args)  # pyright: ignore[reportUnknownMemberType]
                except Exception:
                    # Final resilient fallback directly evaluating the Lua script
                    return await client.eval(script_content, numkeys, *keys_and_args)  # pyright: ignore[reportUnknownMemberType]
            raise LuaScriptError(
                f"Failed to execute Lua script '{script_name}': {exc}"
            ) from exc


@lru_cache
def get_lua_script_manager() -> LuaScriptManager:
    """Retrieve singleton instance of LuaScriptManager with preloaded scripts."""
    return LuaScriptManager()
