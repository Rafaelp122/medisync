#!/usr/bin/env python3
"""Validate documentation links, code snippet lengths, and SSOT stack versions.

Enforces:
- Single Source of Truth (SSOT): PostgreSQL, Valkey, and Python versions match
  docker-compose.yml and pyproject.toml dynamically across all markdown files.
- Markdown links [label](target.md) resolve to existing files.
- Backtick paths `src/...`, `docs/...` resolve to existing files.
- Parity of modules: all Bounded Contexts in src/modules/ are in README.md.
- Tooling parity: all `just <cmd>` in README.md are defined in justfile.
- Forbidden legacy terms: event_bus.py and In-Memory Event Bus are banned.
- Python code blocks <= 5 lines outside of reference/, adrs/, and how-to/.
- Mandatory 5 sections for reference documents in docs/reference/.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATH_RE = re.compile(r"`((?:src|docs|tests)/[^`:\s#]+)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
FENCE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
PYTHON_FENCE_RE = re.compile(r"```python(.*?)```", re.DOTALL)

POSTGRES_VERSION_RE = re.compile(r"\b(?:PostgreSQL|Postgres)\s+(\d+)\b")
VALKEY_VERSION_RE = re.compile(r"\bValkey\s+(\d+(?:\.\d+)?\+?)\b")
PYTHON_VERSION_RE = re.compile(r"\bPython\s+(\d+\.\d+)(?:\+|(?:\s+ou\s+superior))?\b")

# Diretórios autorizados a conter blocos Python explicativos > 5 linhas
ALLOWED_PYTHON_DIRS = (
    "docs/reference",
    "docs/adrs",
    "docs/how-to",
)

# Template obrigatório de 5 seções para o quadrante Reference
MANDATORY_REFERENCE_SECTIONS = [
    "## Contexto",
    "## Conceito",
    "## Onde no código",
    "## Verificação",
    "## Ver também",
]

# Arquivos de referência com refatoração de template pendente
REFERENCE_EXEMPT_FILES: set[str] = set()


def _get_ssot_versions() -> tuple[str, str, str]:
    """Extract canonical versions from pyproject.toml and docker-compose.yml."""
    pyproject_path = ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)

    requires_python = str(pyproject.get("project", {}).get("requires-python", ">=3.12"))
    python_match = re.search(r"(\d+\.\d+)", requires_python)
    expected_python = python_match.group(1) if python_match else "3.12"

    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    pg_match = re.search(r"image:\s*postgres:(\d+)", compose_text)
    expected_pg = pg_match.group(1) if pg_match else "17"

    valkey_match = re.search(r"image:\s*valkey/valkey:([\d.]+)", compose_text)
    expected_valkey = valkey_match.group(1) if valkey_match else "8.0"

    return expected_python, expected_pg, expected_valkey


def _is_lower_version(v1: str, v2: str) -> bool:
    try:
        p1 = tuple(int(x) for x in v1.split("."))
        p2 = tuple(int(x) for x in v2.split("."))
        return p1 < p2
    except ValueError:
        return False


def main() -> int:
    errors: list[str] = []

    expected_python, expected_pg, expected_valkey = _get_ssot_versions()

    # Todos os arquivos markdown: docs/ e README.md
    md_files = sorted((ROOT / "docs").rglob("*.md"))
    readme_path = ROOT / "README.md"
    if readme_path.exists():
        md_files.append(readme_path)

    for md in md_files:
        rel_posix = md.relative_to(ROOT).as_posix()
        text = md.read_text(encoding="utf-8")
        text_no_fences = FENCE_BLOCK_RE.sub("", text)

        # 1. Referências a arquivos entre crases (`src/...`, `docs/...`, `tests/...`)
        for m in PATH_RE.finditer(text_no_fences):
            ref = m.group(1).split("#")[0].strip()
            # Ignora curingas (*), placeholders (<modulo>) e reticências (...)
            if any(char in ref for char in ("*", "<", ">")) or "..." in ref:
                continue
            if not (ROOT / ref).exists():
                errors.append(f"{rel_posix}: missing path `{ref}`")

        # 2. Links nativos markdown [label](target.md) com resolução relativa
        for m in MD_LINK_RE.finditer(text_no_fences):
            label = m.group(1)
            target = m.group(2).strip()
            if target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
                continue
            clean_target = target.split("#")[0].strip()
            if not clean_target:
                continue
            if clean_target.startswith("file://"):
                target_file = Path(clean_target[7:])
            elif clean_target.startswith("/"):
                target_file = ROOT / clean_target.lstrip("/")
            else:
                target_file = (md.parent / clean_target).resolve()

            if not target_file.exists():
                errors.append(f"{rel_posix}: missing link target [{label}]({target})")

        # 3. Checagem de blocos python >5 linhas fora de reference/, adrs e how-to
        if (
            not any(rel_posix.startswith(d) for d in ALLOWED_PYTHON_DIRS)
            and rel_posix != "README.md"
        ):
            for m in PYTHON_FENCE_RE.finditer(text):
                lines = [ln for ln in m.group(1).strip().splitlines() if ln.strip()]
                if len(lines) > 5:
                    errors.append(f"{rel_posix}: python block {len(lines)} lines >5")

        # 4. Validação de seções obrigatórias para docs/reference/*.md
        if (
            rel_posix.startswith("docs/reference/")
            and md.name != "index.md"
            and rel_posix not in REFERENCE_EXEMPT_FILES
        ):
            for sec in MANDATORY_REFERENCE_SECTIONS:
                if sec not in text:
                    errors.append(f'{rel_posix}: missing mandatory section "{sec}"')

        # 5. SSOT: Validação dinâmica de versões da Stack (PostgreSQL)
        for m in POSTGRES_VERSION_RE.finditer(text_no_fences):
            found_pg = m.group(1)
            if found_pg != expected_pg:
                errors.append(
                    f"{rel_posix}: PostgreSQL version mismatch: found '{found_pg}', "
                    f"expected '{expected_pg}' (from docker-compose.yml)"
                )

        # 6. SSOT: Validação dinâmica de versões da Stack (Valkey)
        for m in VALKEY_VERSION_RE.finditer(text_no_fences):
            found_vk = m.group(1)
            expected_major = expected_valkey.split(".")[0]
            if found_vk not in (expected_valkey, expected_major):
                errors.append(
                    f"{rel_posix}: Valkey version mismatch: found '{found_vk}', "
                    f"expected '{expected_valkey}' (from docker-compose.yml)"
                )

        # 7. SSOT: Validação dinâmica de versões de Python
        for m in PYTHON_VERSION_RE.finditer(text_no_fences):
            found_py = m.group(1)
            if _is_lower_version(found_py, expected_python):
                errors.append(
                    f"{rel_posix}: unsupported Python version '{found_py}': "
                    f"minimum expected is '{expected_python}' (from pyproject.toml)"
                )

        # 8. Bloqueio de termos obsoletos / arquivos fantasmas
        if (
            "event_bus.py" in text_no_fences
            and rel_posix != "docs/explanation/domains/domain-events.md"
        ):
            errors.append(
                f"{rel_posix}: forbidden reference to non-existent 'event_bus.py'"
            )
        if "In-Memory Event Bus" in text:
            errors.append(
                f"{rel_posix}: forbidden reference to deprecated 'In-Memory Event Bus'"
            )

    # 9. Paridade modular dinâmica no README.md
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        modules_dir = ROOT / "src" / "modules"
        if modules_dir.exists():
            actual_modules = sorted(
                [
                    d.name
                    for d in modules_dir.iterdir()
                    if d.is_dir() and not d.name.startswith((".", "__"))
                ]
            )
            for mod in actual_modules:
                if f"modules/{mod}" not in readme_text and f"{mod}/" not in readme_text:
                    errors.append(
                        f"README.md: missing module mention for '{mod}' "
                        f"(expected all modules in src/modules/ to be documented)"
                    )

        # 10. Consistência de comandos just no README.md
        justfile_path = ROOT / "justfile"
        if justfile_path.exists():
            justfile_text = justfile_path.read_text(encoding="utf-8")
            defined_recipes = set(
                re.findall(
                    r"^([a-zA-Z0-9_-]+)(?:\s+[^:]*)?:", justfile_text, re.MULTILINE
                )
            )
            just_commands = re.findall(r"\bjust\s+([a-zA-Z0-9_-]+)\b", readme_text)
            for cmd in sorted(set(just_commands)):
                if cmd not in defined_recipes:
                    errors.append(
                        f"README.md: unknown just command 'just {cmd}' "
                        f"(recipe not defined in justfile)"
                    )

    for e in errors:
        print(e)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
