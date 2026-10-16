"""Architectural guards for services and composition roots (ADR-001 & ADR-009).

Scans:
1. ``src/modules/*/application/services/*.py``:
   - Must NEVER import ``get_settings`` or ``src.core.config``.
   - Dependencies must be passed via __init__ (clean constructors).
2. ``src/modules/*/composition.py``:
   - Must NEVER use ``global`` statements (no mutable singletons).
   - Must NEVER import presentation layers.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_MODULES = REPO_ROOT / "src" / "modules"


def _service_files() -> list[Path]:
    files = sorted(SRC_MODULES.glob("*/application/services/*.py"))
    assert files, "no service files found under src/modules/*/application/services/"
    return [f for f in files if f.name != "__pycache__"]


def _composition_files() -> list[Path]:
    files = sorted(SRC_MODULES.glob("*/composition.py"))
    assert files, "no composition files found under src/modules/*/composition.py"
    return [f for f in files if f.name != "__pycache__"]


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_services_do_not_import_config_or_get_settings() -> None:
    violations: list[str] = []
    for path in _service_files():
        tree = _parse(path)
        rel_path = path.relative_to(REPO_ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "src.core.config" in alias.name:
                        violations.append(
                            f"{rel_path}:{node.lineno} import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "src.core.config" in mod or any(
                    alias.name == "get_settings" for alias in node.names
                ):
                    imported = ", ".join(alias.name for alias in node.names)
                    violations.append(
                        f"{rel_path}:{node.lineno} from {mod} import {imported}"
                    )
    msg = (
        "Application services must not import get_settings/config "
        "directly (inject via constructor):\n"
    )
    assert not violations, msg + "\n".join(violations)


def test_composition_roots_have_no_mutable_globals() -> None:
    violations: list[str] = []
    for path in _composition_files():
        tree = _parse(path)
        rel_path = path.relative_to(REPO_ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                names = ", ".join(node.names)
                violations.append(f"{rel_path}:{node.lineno} global {names}")
    msg = (
        "Composition roots must not use mutable global singletons "
        "(resolve dynamically):\n"
    )
    assert not violations, msg + "\n".join(violations)


def test_composition_roots_do_not_import_presentation() -> None:
    violations: list[str] = []
    for path in _composition_files():
        tree = _parse(path)
        rel_path = path.relative_to(REPO_ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "presentation" in alias.name:
                        violations.append(
                            f"{rel_path}:{node.lineno} import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "presentation" in mod:
                    imported = ", ".join(alias.name for alias in node.names)
                    violations.append(
                        f"{rel_path}:{node.lineno} from {mod} import {imported}"
                    )
    assert not violations, (
        "Composition roots must not import presentation layers:\n"
        + "\n".join(violations)
    )
