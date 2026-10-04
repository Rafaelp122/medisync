"""Architectural guard: routers stay thin (ADR-001).

Scans every ``src/modules/*/presentation/routers/*.py`` with AST (stdlib only)
and fails on layering leaks:

- no ``sqlalchemy`` / ``infrastructure`` / ``domain.models`` imports
- no ``.commit(`` / ``.refresh(`` / ``text(`` / ``select(`` calls
- no ``HTTPException`` (only allowed in ``presentation/dependencies.py``)
- no direct ``*Service(`` instantiation (services arrive via composition Deps)
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "modules"


def _router_files() -> list[Path]:
    files = sorted((SRC_ROOT).glob("*/presentation/routers/*.py"))
    assert files, "no router files found under src/modules/*/presentation/routers/"
    return [f for f in files if f.name != "__pycache__"]


def _presentation_files() -> list[Path]:
    return sorted(SRC_ROOT.glob("*/presentation/**/*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_routers_do_not_import_forbidden_layers() -> None:
    banned = ("sqlalchemy", "infrastructure", "domain.models")
    violations: list[str] = []
    for path in _router_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(b in alias.name for b in banned):
                        violations.append(f"{path}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if any(b in mod for b in banned):
                    violations.append(f"{path}:{node.lineno} from {mod} import ...")
    assert not violations, "router imports forbidden layer:\n" + "\n".join(violations)


def test_routers_have_no_commit_refresh_text_select() -> None:
    violations: list[str] = []
    for path in _router_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in {
                    "commit",
                    "refresh",
                }:
                    violations.append(f"{path}:{node.lineno} .{func.attr}()")
                elif isinstance(func, ast.Name) and func.id in {"text", "select"}:
                    violations.append(f"{path}:{node.lineno} {func.id}()")
    assert not violations, "router executes persistence call:\n" + "\n".join(violations)


def test_routers_have_no_http_exception() -> None:
    violations: list[str] = []
    for path in _router_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "HTTPException":
                        violations.append(f"{path}:{node.lineno} imports HTTPException")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "HTTPException" in alias.name:
                        violations.append(f"{path}:{node.lineno} imports HTTPException")
            elif isinstance(node, ast.Name) and node.id == "HTTPException":
                violations.append(f"{path}:{node.lineno} uses HTTPException")
    assert not violations, (
        "router must not raise HTTPException (use dependencies.py):\n"
        + "\n".join(violations)
    )


def test_routers_do_not_instantiate_services() -> None:
    violations: list[str] = []
    for path in _router_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name.endswith("Service") and name != "Service":
                    violations.append(f"{path}:{node.lineno} instantiates {name}()")
    assert not violations, (
        "router must not instantiate services (use composition Deps):\n"
        + "\n".join(violations)
    )


def test_http_exception_only_in_dependencies() -> None:
    """HTTPException may appear only in presentation/dependencies.py."""
    violations: list[str] = []
    for path in _presentation_files():
        if path.name == "dependencies.py":
            continue
        if "routers" not in path.parts and path.name not in {
            "helpers.py",
            "schemas.py",
            "__init__.py",
        }:
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "HTTPException":
                        violations.append(f"{path}:{node.lineno} imports HTTPException")
            elif isinstance(node, ast.Name) and node.id == "HTTPException":
                violations.append(f"{path}:{node.lineno} uses HTTPException")
    assert not violations, (
        "HTTPException allowed only in presentation/dependencies.py:\n"
        + "\n".join(violations)
    )
