"""Unit tests for scripts/scaffold_module.py."""

from pathlib import Path

import pytest
from scripts.scaffold_module import (
    register_tach_boundaries,
    scaffold_module,
    validate_module_name,
)


def test_validate_module_name_invalid_format(tmp_path: Path) -> None:
    for invalid in ["Prontuario", "prontuario-eletronico", "1prontuario", "prontu@rio"]:
        with pytest.raises(ValueError, match="inválido"):
            validate_module_name(invalid, tmp_path)


def test_validate_module_name_reserved(tmp_path: Path) -> None:
    for reserved in ["core", "worker", "def", "class", "import"]:
        with pytest.raises(ValueError, match="palavra reservada"):
            validate_module_name(reserved, tmp_path)


def test_validate_module_name_already_exists(tmp_path: Path) -> None:
    target = tmp_path / "src" / "modules" / "existente"
    target.mkdir(parents=True, exist_ok=True)

    with pytest.raises(FileExistsError, match="já existe"):
        validate_module_name("existente", tmp_path)


def test_scaffold_module_full_flow(tmp_path: Path) -> None:
    tach_file = tmp_path / "tach.toml"
    tach_file.write_text("interfaces = []\nexact = false\n", encoding="utf-8")

    scaffold_module("paciente_prontuario", root_dir=tmp_path)

    # 1. Check directories
    module_dir = tmp_path / "src" / "modules" / "paciente_prontuario"
    assert (module_dir / "__init__.py").exists()
    assert (module_dir / "composition.py").exists()
    assert (module_dir / "domain" / "models.py").exists()
    assert (module_dir / "domain" / "exceptions.py").exists()
    assert (module_dir / "application" / "dtos.py").exists()
    assert (module_dir / "application" / "ports" / "__init__.py").exists()
    assert (module_dir / "application" / "services" / "__init__.py").exists()
    assert (module_dir / "infrastructure" / "adapters" / "__init__.py").exists()
    assert (module_dir / "presentation" / "schemas.py").exists()
    assert (module_dir / "presentation" / "dependencies.py").exists()
    assert (module_dir / "presentation" / "routers" / "__init__.py").exists()

    # 2. Check test stubs
    assert (
        tmp_path / "tests" / "unit" / "test_paciente_prontuario_service.py"
    ).exists()
    assert (tmp_path / "tests" / "unit" / "test_paciente_prontuario_router.py").exists()

    # 3. Check Diataxis doc stub
    doc_path = (
        tmp_path / "docs" / "explanation" / "domains" / "paciente_prontuario-domain.md"
    )
    assert doc_path.exists()
    doc_content = doc_path.read_text(encoding="utf-8")
    assert "## 1. Visão Geral e Conceito" in doc_content
    assert "## 2. Regras de Negócio Canônicas" in doc_content
    assert "## 3. Arquitetura e Portas Hexagonais" in doc_content
    assert "## 4. Contratos e Apresentação" in doc_content
    assert "## 5. Rastreabilidade e Verificação" in doc_content

    # 4. Check tach.toml
    tach_content = tach_file.read_text(encoding="utf-8")
    assert 'path = "src.modules.paciente_prontuario.domain"' in tach_content
    assert 'path = "src.modules.paciente_prontuario.application"' in tach_content
    assert 'path = "src.modules.paciente_prontuario.infrastructure"' in tach_content
    assert 'path = "src.modules.paciente_prontuario.composition"' in tach_content
    assert 'path = "src.modules.paciente_prontuario.presentation"' in tach_content


def test_register_tach_boundaries_idempotent(tmp_path: Path) -> None:
    tach_file = tmp_path / "tach.toml"
    tach_file.write_text("interfaces = []\nexact = false\n", encoding="utf-8")

    registered_first = register_tach_boundaries("modulo_teste", tmp_path)
    assert registered_first is True

    registered_second = register_tach_boundaries("modulo_teste", tmp_path)
    assert registered_second is False
