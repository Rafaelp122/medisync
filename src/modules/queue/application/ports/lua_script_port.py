"""Port specification for atomic Valkey Lua script execution."""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LuaScriptPort(Protocol):
    """Port interface for executing cached Lua scripts with auto-healing."""

    async def execute_script(
        self,
        client: Any,
        script_name: str,
        keys: Sequence[str] = (),
        args: Sequence[Any] = (),
    ) -> Any:
        """Execute a registered Lua script via EVALSHA with NOSCRIPT healing.

        Args:
            client: Active Valkey/Redis async client.
            script_name: Registered script name (Lua file stem).
            keys: KEYS array for the script.
            args: ARGV array for the script.

        Returns:
            Raw script result (integer return code for allocation scripts).
        """
        ...
