#!/usr/bin/env python3
"""Fail if docs reference missing src/docs paths or paste code >5 lines."""
from __future__ import annotations
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PATH_RE = re.compile(r"`((?:src|docs|tests)/[^`:\s]+)")
FENCE_RE = re.compile(r"```python(.*?)```", re.DOTALL)
def main() -> int:
    errors: list[str] = []
    for md in (ROOT / "docs").rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for m in PATH_RE.finditer(text):
            ref = m.group(1).split("#")[0]
            if not (ROOT / ref).exists():
                errors.append(f"{md.relative_to(ROOT)}: missing {ref}")
        for m in FENCE_RE.finditer(text):
            lines = [ln for ln in m.group(1).strip().splitlines() if ln.strip()]
            if len(lines) > 5 and "reference/" not in str(md):
                errors.append(f"{md.relative_to(ROOT)}: python block {len(lines)} lines >5")
    for e in errors: print(e)
    return 1 if errors else 0
if __name__ == "__main__": sys.exit(main())
