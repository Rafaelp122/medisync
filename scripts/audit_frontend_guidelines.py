#!/usr/bin/env python3
"""Auditoria estática de diretrizes de frontend (Vercel Guidelines & ADR-011).

Regras verificadas:
1. Regra (a): Proibição de 'transition: all' e Tailwind 'transition-all'.
2. Regra (b): Detecção de reticências ASCII '...' em textos JSX ou strings de UI.
3. Regra (c): Proibição de barrel imports de '@/api/generated'.
4. Regra (d): Proibição de imports cruzados diretos entre features (@/features/*).
5. Regra (e): Presença de <meta name="theme-color"> e 'color-scheme'.

Saída:
Formato canônico da Vercel: 'file:line - finding'. Código != 0 em caso de erro.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
SRC_DIR = FRONTEND_DIR / "src"
INDEX_HTML = FRONTEND_DIR / "index.html"
GLOBALS_CSS = SRC_DIR / "globals.css"

EXCLUDED_PARTS = {"api/generated", "node_modules", "dist", ".git", ".next"}

# Regexes de Regras
RE_TRANSITION_ALL_CSS = re.compile(r"\btransition\s*:[^;]*\ball\b")
RE_TRANSITION_ALL_CLASS = re.compile(r"\btransition-all\b")

# Reticências ASCII '...' em textos JSX visíveis ou strings com palavras
RE_JSX_TEXT_ELLIPSIS = re.compile(r">([^<{}]*?\w\s*\.{3}[^<{}]*?)<")
RE_STRING_LITERAL_ELLIPSIS = re.compile(
    r"""(?:["'`])([^"'`\n]*?[a-zA-ZÀ-ÿ0-9]\s*\.{3}[^"'`\n]*?)(?:["'`])"""
)

# Barrel imports de api/generated
RE_BARREL_IMPORT = re.compile(
    r"""(?:import|export)\s+.*?from\s+['"](@/api/generated(?:/index(?:\.ts)?)?|(?:\.\./)+api/generated(?:/index(?:\.ts)?)?)['"]"""
)

# Imports de features
RE_FEATURE_IMPORT = re.compile(
    r"""(?:import|export)\s+.*?from\s+['"]@/features/([^/'"]+)"""
)
RE_RELATIVE_FEATURE_IMPORT = re.compile(
    r"""(?:import|export)\s+.*?from\s+['"](?:\.\./)+features/([^/'"]+)"""
)


MAX_COMPONENT_LINES = 300


@dataclass(frozen=True)
class Finding:
    filepath: Path
    line: int
    message: str


def audit_component_line_length(path: Path, lines: list[str]) -> str | None:
    """Verifica se um componente visual TSX excede o teto recomendado de 300 linhas."""
    posix = path.as_posix()
    if not (
        path.suffix in {".tsx", ".jsx"}
        and ("features" in posix or "components" in posix)
        and not posix.endswith((".test.tsx", ".test.jsx", ".spec.tsx", ".spec.jsx"))
    ):
        return None

    total_lines = len(lines)
    if total_lines > MAX_COMPONENT_LINES:
        return (
            f"Componente excede {MAX_COMPONENT_LINES} linhas ({total_lines} linhas) "
            "→ considere decompor em compound components"
        )
    return None


def strip_code_comments(line: str) -> str:
    """Remove comentários inline simples para evitar falsos positivos."""
    stripped = line.strip()
    if (
        stripped.startswith("//")
        or stripped.startswith("/*")
        or stripped.startswith("*")
    ):
        return ""
    if "//" in line:
        return line.split("//")[0]
    return line


def _audit_line_ellipses(
    rel_path: Path, line_idx: int, clean_line: str
) -> list[Finding]:
    """Valida presença de reticências ASCII '...' em texto de UI JSX (Regra b)."""
    findings: list[Finding] = []
    for m in RE_JSX_TEXT_ELLIPSIS.finditer(clean_line):
        snippet = m.group(1).strip()
        msg = f'"{snippet}" → "…" (use typographical ellipsis)'
        findings.append(Finding(rel_path, line_idx, msg))

    for m in RE_STRING_LITERAL_ELLIPSIS.finditer(clean_line):
        snippet = m.group(1).strip()
        if snippet.startswith("http") or snippet.startswith("..."):
            continue
        if re.search(r"[a-zA-ZÀ-ÿ]", snippet):
            msg = f'"{snippet}" → "…" (use typographical ellipsis)'
            findings.append(Finding(rel_path, line_idx, msg))
    return findings


def _audit_cross_feature_imports(
    rel_path: Path, line_idx: int, clean_line: str, current_feature: str
) -> list[Finding]:
    """Valida proibição de imports cruzados diretos entre features (Regra d)."""
    findings: list[Finding] = []
    for m in RE_FEATURE_IMPORT.finditer(clean_line):
        target_feat = m.group(1)
        if target_feat != current_feature:
            findings.append(
                Finding(
                    rel_path,
                    line_idx,
                    f"cross-feature import '@/{target_feat}' forbidden",
                )
            )
    for m in RE_RELATIVE_FEATURE_IMPORT.finditer(clean_line):
        target_feat = m.group(1)
        if target_feat != current_feature:
            findings.append(
                Finding(
                    rel_path, line_idx, f"relative import to '{target_feat}' forbidden"
                )
            )
    return findings


def audit_file_content(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel_path = path.relative_to(ROOT)
    is_tsx = path.suffix in {".tsx", ".jsx"}
    is_ts_or_tsx = path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    is_css = path.suffix == ".css"

    # Identifica a feature atual para validação de fronteira (Regra d)
    current_feature: str | None = None
    try:
        rel_to_src = path.relative_to(SRC_DIR)
        parts = rel_to_src.parts
        if len(parts) >= 2 and parts[0] == "features":
            current_feature = parts[1]
    except ValueError:
        pass

    for line_idx, raw_line in enumerate(lines, start=1):
        clean_line = strip_code_comments(raw_line)
        if not clean_line:
            continue

        # Regra (a): transition-all ou transition: all
        if is_css and RE_TRANSITION_ALL_CSS.search(clean_line):
            msg = "transition: all → list properties explicitly"
            findings.append(Finding(rel_path, line_idx, msg))
        elif is_ts_or_tsx and (
            RE_TRANSITION_ALL_CLASS.search(clean_line)
            or RE_TRANSITION_ALL_CSS.search(clean_line)
        ):
            msg = "transition-all → list properties explicitly"
            findings.append(Finding(rel_path, line_idx, msg))

        # Regra (b): Reticências ASCII '...' em texto de UI
        if is_tsx:
            findings.extend(_audit_line_ellipses(rel_path, line_idx, clean_line))

        # Regra (c): Barrel imports de @/api/generated
        if is_ts_or_tsx:
            for _ in RE_BARREL_IMPORT.finditer(clean_line):
                msg = "barrel import forbidden → import from leaf files"
                findings.append(Finding(rel_path, line_idx, msg))

        # Regra (d): Imports cruzados diretos entre features
        if is_ts_or_tsx and current_feature:
            findings.extend(
                _audit_cross_feature_imports(
                    rel_path, line_idx, clean_line, current_feature
                )
            )

    return findings


def audit_theme_and_color_scheme() -> list[Finding]:
    """Regra (e): Validação de <meta name='theme-color'> e color-scheme."""
    findings: list[Finding] = []
    rel_html = INDEX_HTML.relative_to(ROOT)

    if not INDEX_HTML.exists():
        findings.append(Finding(rel_html, 1, "missing frontend/index.html"))
        return findings

    html_content = INDEX_HTML.read_text(encoding="utf-8")

    has_theme_color = bool(
        re.search(
            r'<meta[^>]+name=["\']theme-color["\'][^>]*>',
            html_content,
            re.IGNORECASE,
        )
        or re.search(
            r'<meta[^>]+content=["\'][^"\']+["\'][^>]+name=["\']theme-color["\']',
            html_content,
            re.IGNORECASE,
        )
    )
    if not has_theme_color:
        findings.append(
            Finding(rel_html, 1, 'missing <meta name="theme-color"> in <head>')
        )

    has_color_scheme = bool(
        re.search(r'<meta[^>]+name=["\']color-scheme["\']', html_content, re.IGNORECASE)
        or (
            GLOBALS_CSS.exists()
            and re.search(
                r"\bcolor-scheme\s*:", GLOBALS_CSS.read_text(encoding="utf-8")
            )
        )
    )
    if not has_color_scheme:
        findings.append(
            Finding(
                rel_html,
                1,
                "missing color-scheme (in <meta name='color-scheme'> or globals.css)",
            )
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditoria de Diretrizes de Frontend (Vercel Guidelines & ADR-011)"
    )
    parser.parse_args()

    if not FRONTEND_DIR.exists():
        print("Diretório frontend/ não encontrado. Pulando auditoria.")
        return 0

    all_findings: list[Finding] = []
    warnings: list[tuple[Path, str]] = []
    scanned_files = 0

    # Varre frontend/src
    for path in sorted(SRC_DIR.rglob("*")):
        if not path.is_file():
            continue
        posix = path.as_posix()
        if any(part in posix for part in EXCLUDED_PARTS):
            continue
        if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".css"}:
            scanned_files += 1
            all_findings.extend(audit_file_content(path))
            if path.suffix in {".tsx", ".jsx"}:
                warn = audit_component_line_length(
                    path, path.read_text(encoding="utf-8").splitlines()
                )
                if warn:
                    warnings.append((path.relative_to(ROOT), warn))

    # Varre index.html e tema
    if INDEX_HTML.exists():
        scanned_files += 1
        all_findings.extend(audit_theme_and_color_scheme())

    # Agrupamento e saída no formato canônico da Vercel
    grouped: dict[Path, list[Finding]] = defaultdict(list)
    for f in all_findings:
        grouped[f.filepath].append(f)

    print("\n" + "=" * 70)
    print("🎨 RELATÓRIO DE AUDITORIA: FRONTEND GUIDELINES (VERCEL & ADR-011)")
    print("=" * 70)
    print(f"Arquivos analisados em {SRC_DIR.relative_to(ROOT)}: {scanned_files}")

    if warnings:
        print(f"\n⚠️  {len(warnings)} avisos de complexidade (>300 linhas):")
        for fpath, msg in sorted(warnings, key=lambda x: str(x[0])):
            print(f"  - {fpath.as_posix()}: {msg}")

    if not all_findings:
        print("\n✅ 100% em conformidade com as diretrizes de frontend!")
        print("=" * 70 + "\n")
        return 0

    print(
        f"\n❌ {len(all_findings)} violações encontradas em {len(grouped)} arquivos:\n"
    )
    for filepath, findings in sorted(grouped.items(), key=lambda x: str(x[0])):
        print(f"## {filepath.as_posix()}\n")
        for f in findings:
            print(f"{f.filepath.as_posix()}:{f.line} - {f.message}")
        print()

    print("=" * 70)
    print("❌ Falha na auditoria de diretrizes de frontend.")
    print("=" * 70 + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
