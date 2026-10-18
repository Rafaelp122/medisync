"""Auditoria de conformidade com os princípios de Clean Code para Agentes de IA.

Verifica:
1. Aninhamento de controle de fluxo raso (máximo 2 níveis por função).
2. Exceções ricas com valor ofensivo e expected shape (anti-naked-strings).
3. Rastreabilidade de proveniência atômica em métodos públicos de negócio
   (RN/RF/ADR/docs).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path


class AIAuditVisitor:
    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.nesting_violations: list[tuple[str, int, int]] = []
        self.naked_raises: list[tuple[int, str, str]] = []
        self.public_business_methods: list[tuple[str, int, bool, str]] = []

    def audit(self, tree: ast.AST) -> None:
        is_business_file = "application/services" in str(
            self.filepath
        ) or "domain/models" in str(self.filepath)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_nesting(node)
                if is_business_file and not node.name.startswith("_"):
                    self._check_business_docstring(node)
            elif isinstance(node, ast.Raise):
                self._check_raise(node)

    def _check_nesting(self, fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        def get_depth(node: ast.AST, current: int = 0) -> int:
            max_d = current
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match)
                ):
                    d = get_depth(child, current + 1)
                    max_d = max(max_d, d)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                else:
                    d = get_depth(child, current)
                    max_d = max(max_d, d)
            return max_d

        depth = get_depth(fn_node, 0)
        if depth > 2:
            self.nesting_violations.append((fn_node.name, fn_node.lineno, depth))

    def _check_raise(self, raise_node: ast.Raise) -> None:
        if not isinstance(raise_node.exc, ast.Call):
            return

        exc_func = raise_node.exc.func
        exc_name = getattr(exc_func, "id", getattr(exc_func, "attr", "Unknown"))
        args = raise_node.exc.args

        if not args:
            return

        first_arg = args[0]
        # Se for string constante estática sem interpolação
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            msg = first_arg.value
            # Exceções técnicas genéricas que justificam mensagem estática
            if exc_name in {"NotImplementedError", "KeyboardInterrupt"}:
                return
            self.naked_raises.append((raise_node.lineno, exc_name, msg))

    def _check_business_docstring(
        self, fn_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        doc = ast.get_docstring(fn_node)
        has_rule = False
        summary = ""
        if doc:
            summary = doc.strip().split("\n")[0]
            if re.search(r"(RN\d+|RF-\d+|ADR-\d+|CFM|LGPD|Portaria|docs/)", doc):
                has_rule = True
        self.public_business_methods.append(
            (fn_node.name, fn_node.lineno, has_rule, summary)
        )


def run_audit(src_dir: Path) -> int:
    total_files = 0
    all_nesting: list[tuple[Path, str, int, int]] = []
    all_naked_raises: list[tuple[Path, int, str, str]] = []
    all_business_methods: list[tuple[Path, str, int, bool, str]] = []

    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith(".py"):
                filepath = Path(root) / file
                total_files += 1
                try:
                    tree = ast.parse(
                        filepath.read_text(encoding="utf-8"), filename=str(filepath)
                    )
                except Exception as e:
                    print(f"Erro ao parsear {filepath}: {e}", file=sys.stderr)
                    continue

                visitor = AIAuditVisitor(filepath)
                visitor.audit(tree)

                for name, lineno, depth in visitor.nesting_violations:
                    all_nesting.append((filepath, name, lineno, depth))
                for lineno, exc, msg in visitor.naked_raises:
                    all_naked_raises.append((filepath, lineno, exc, msg))
                for name, lineno, has_rule, summary in visitor.public_business_methods:
                    all_business_methods.append(
                        (filepath, name, lineno, has_rule, summary)
                    )

    print("\n" + "=" * 70)
    print("🤖 RELATÓRIO DE AUDITORIA: CLEAN CODE PARA AGENTES DE IA")
    print("=" * 70)
    print(f"Arquivos analisados em {src_dir}: {total_files}")

    print("\n1. Aninhamento de Controle de Fluxo (Teto: Max 2 níveis):")
    if not all_nesting:
        print("   ✅ 100% em conformidade! Nenhuma função com depth > 2.")
    else:
        print(f"   ⚠️  {len(all_nesting)} funções com aninhamento > 2:")
        for fp, name, lineno, depth in sorted(
            all_nesting, key=lambda x: x[3], reverse=True
        )[:15]:
            rel_path = fp.relative_to(src_dir.parent)
            print(f"      - {rel_path}:{lineno} {name}() (depth={depth})")
        if len(all_nesting) > 15:
            print(f"      ... e mais {len(all_nesting) - 15} funções.")

    print("\n2. Exceções com Contexto do Valor Ofensivo (Offending Value):")
    if not all_naked_raises:
        print("   ✅ 100% em conformidade! Zero raises estáticos sem valor ofensivo.")
    else:
        print(f"   ⚠️  {len(all_naked_raises)} raises com strings estáticas cegas:")
        for fp, lineno, exc, msg in all_naked_raises[:10]:
            rel_path = fp.relative_to(src_dir.parent)
            snippet = msg if len(msg) <= 50 else msg[:47] + "..."
            print(f'      - {rel_path}:{lineno} raise {exc}("{snippet}")')
        if len(all_naked_raises) > 10:
            print(f"      ... e mais {len(all_naked_raises) - 10} ocorrências.")

    print("\n3. Rastreabilidade de Regras em Métodos Públicos de Negócio:")
    if all_business_methods:
        with_rules = [m for m in all_business_methods if m[3]]
        coverage = (len(with_rules) / len(all_business_methods)) * 100
        count_str = f"{len(with_rules)}/{len(all_business_methods)}"
        print(f"   📊 Cobertura de Proveniência: {count_str} métodos ({coverage:.1f}%)")
        without_rules = [m for m in all_business_methods if not m[3]]
        if without_rules:
            print("   ⚠️  Exemplos sem link de regra/ADR em docstring:")
            for fp, name, lineno, _, _ in without_rules[:8]:
                rel_path = fp.relative_to(src_dir.parent)
                print(f"      - {rel_path}:{lineno} {name}()")
    else:
        print("   [i] Nenhum método público de negócio identificado.")

    print("\n" + "=" * 70 + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria de Clean Code para IA")
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("src"),
        help="Diretório fonte para auditar (default: src)",
    )
    args = parser.parse_args()
    return run_audit(args.src)


if __name__ == "__main__":
    sys.exit(main())
