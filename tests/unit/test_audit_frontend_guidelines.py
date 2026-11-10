"""Unit tests for frontend guidelines audit script."""

from pathlib import Path

from scripts.audit_frontend_guidelines import (
    MAX_COMPONENT_LINES,
    audit_component_line_length,
)


def test_audit_flags_files_exceeding_300_lines_as_warning(tmp_path: Path) -> None:
    component_file = (
        tmp_path
        / "frontend"
        / "src"
        / "features"
        / "queue"
        / "components"
        / "big-card.tsx"
    )
    component_file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["export function BigCard() {\n"] * (MAX_COMPONENT_LINES + 5)
    component_file.write_text("".join(lines), encoding="utf-8")

    warning = audit_component_line_length(component_file, lines)
    assert warning is not None
    assert f"{MAX_COMPONENT_LINES + 5} linhas" in warning or "excede" in warning.lower()
    assert "compound" in warning.lower()


def test_audit_passes_valid_sized_components_without_warning(tmp_path: Path) -> None:
    component_file = (
        tmp_path
        / "frontend"
        / "src"
        / "features"
        / "queue"
        / "components"
        / "small-card.tsx"
    )
    component_file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["export function SmallCard() {\n"] * 50
    component_file.write_text("".join(lines), encoding="utf-8")

    warning = audit_component_line_length(component_file, lines)
    assert warning is None


def test_audit_ignores_test_files_and_non_components(tmp_path: Path) -> None:
    test_file = (
        tmp_path / "frontend" / "src" / "features" / "queue" / "tests" / "big.test.tsx"
    )
    test_file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["test('big', () => {});\n"] * (MAX_COMPONENT_LINES + 10)
    test_file.write_text("".join(lines), encoding="utf-8")

    warning = audit_component_line_length(test_file, lines)
    assert warning is None
