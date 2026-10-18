#!/usr/bin/env python3
"""Validate documentation links, code snippet lengths, and reference templates.

Enforces:
- Markdown links [label](target.md) resolve to existing files (relative or repo-root).
- Backtick paths `src/...`, `docs/...`, `tests/...` resolve to existing files.
- Python code blocks <= 5 lines outside of reference/, adrs/, and how-to/.
- Mandatory 5 sections for reference documents in docs/reference/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATH_RE = re.compile(r"`((?:src|docs|tests)/[^`:\s#]+)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
FENCE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
PYTHON_FENCE_RE = re.compile(r"```python(.*?)```", re.DOTALL)

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


def main() -> int:
    errors: list[str] = []

    for md in sorted((ROOT / "docs").rglob("*.md")):
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
        if not any(rel_posix.startswith(d) for d in ALLOWED_PYTHON_DIRS):
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

    for e in errors:
        print(e)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
