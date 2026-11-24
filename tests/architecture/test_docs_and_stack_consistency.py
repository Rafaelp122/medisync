"""Architecture guard: SSOT consistency for SemVer, stack, and docs."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from scripts.docs_check import main as docs_check_main
from src.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_semver_consistency() -> None:
    """Ensure version is identical across pyproject.toml, .cz.toml, and config."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
    pyproject_version = pyproject.get("project", {}).get("version")

    cz_path = REPO_ROOT / ".cz.toml"
    with cz_path.open("rb") as f:
        cz = tomllib.load(f)
    cz_version = cz.get("tool", {}).get("commitizen", {}).get("version")

    settings = get_settings()
    app_version = settings.APP_VERSION

    assert pyproject_version, "version missing in pyproject.toml"
    assert cz_version, "version missing in .cz.toml"
    assert pyproject_version == cz_version == app_version, (
        f"SemVer mismatch: pyproject={pyproject_version}, "
        f"cz={cz_version}, app={app_version}"
    )


def test_docs_and_ssot_guardrails_pass() -> None:
    """Ensure all docs pass the SSOT dynamic checks without errors."""
    exit_code = docs_check_main()
    assert exit_code == 0, (
        "scripts/docs_check.py failed; inspect stdout/stderr for details"
    )


def test_readme_contains_all_bounded_contexts() -> None:
    """Ensure all 8 Bounded Contexts in src/modules/ are documented in README.md."""
    modules_dir = REPO_ROOT / "src" / "modules"
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    actual_modules = sorted(
        [
            d.name
            for d in modules_dir.iterdir()
            if d.is_dir() and not d.name.startswith((".", "__"))
        ]
    )
    assert len(actual_modules) == 8, (
        f"Expected 8 bounded context modules, found {len(actual_modules)}: "
        f"{actual_modules}"
    )

    missing_modules: list[str] = []
    for mod in actual_modules:
        if f"modules/{mod}" not in readme_text and f"{mod}/" not in readme_text:
            missing_modules.append(mod)

    assert not missing_modules, (
        f"README.md missing documentation for modules: {missing_modules}"
    )


def test_readme_just_commands_exist_in_justfile() -> None:
    """Ensure all `just <cmd>` referenced in README.md are defined in justfile."""
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    justfile_text = (REPO_ROOT / "justfile").read_text(encoding="utf-8")

    defined_recipes = set(
        re.findall(r"^([a-zA-Z0-9_-]+)(?:\s+[^:]*)?:", justfile_text, re.MULTILINE)
    )
    just_commands = {
        cmd
        for cmd in re.findall(r"\bjust\s+([a-zA-Z0-9_-]+)\b", readme_text)
        if not cmd.startswith("-")
    }

    unknown_commands = just_commands - defined_recipes
    assert not unknown_commands, (
        f"README.md references unknown just commands: {sorted(unknown_commands)}"
    )


def test_justfile_recipes_are_grouped() -> None:
    """Ensure all recipes in justfile are categorized under canonical groups."""
    justfile_text = (REPO_ROOT / "justfile").read_text(encoding="utf-8")
    canonical_groups = {"geral", "infra", "backend", "frontend"}

    current_group: str | None = None
    ungrouped_recipes: list[str] = []
    invalid_grouped_recipes: list[str] = []

    for line in justfile_text.splitlines():
        group_match = re.match(r"^\s*\[group\(['\"]([^'\"]+)['\"]\)\]", line)
        if group_match:
            current_group = group_match.group(1)
            continue

        recipe_match = re.match(r"^([a-zA-Z0-9_-]+)(?:\s+[^:]*)?:", line)
        if recipe_match:
            recipe = recipe_match.group(1)
            if recipe == "default":
                current_group = None
                continue
            if current_group is None:
                ungrouped_recipes.append(recipe)
            elif current_group not in canonical_groups:
                invalid_grouped_recipes.append(f"{recipe} -> {current_group}")
            current_group = None

    assert not ungrouped_recipes, (
        f"Recipes in justfile missing [group('...')]: {ungrouped_recipes}"
    )
    assert not invalid_grouped_recipes, (
        f"Recipes with non-canonical groups: {invalid_grouped_recipes}. "
        f"Expected: {sorted(canonical_groups)}"
    )


def test_justfile_container_and_log_recipes_exist() -> None:
    """Ensure container helper recipes and parameterized logs exist in justfile."""
    justfile_text = (REPO_ROOT / "justfile").read_text(encoding="utf-8")

    expected_recipes = [
        "docker-migrate",
        "docker-seed",
        "docker-shell",
        "docker-test",
    ]
    for recipe in expected_recipes:
        assert re.search(rf"^{recipe}(?:\s+[^:]*)?:", justfile_text, re.MULTILINE), (
            f"Recipe '{recipe}' not found in justfile"
        )

    # Verifica se logs aceita o parâmetro opcional service
    logs_match = re.search(
        r"^logs(?:\s+service=\"[^\"]*\")?:", justfile_text, re.MULTILINE
    )
    assert logs_match is not None, (
        "Recipe 'logs' with optional service parameter not found in justfile"
    )
