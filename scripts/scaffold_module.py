"""Deterministic scaffolding CLI for MediSync Express hexagonal modules.

Creates standard directories, files, unit test stubs, Diátaxis domain doc stubs,
and registers layer boundary contracts into tach.toml.

Usage:
    uv run python scripts/scaffold_module.py <module_name> [--root <path>]
"""

import argparse
import keyword
import re
import sys
from pathlib import Path

_MODULE_NAME_REGEX = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED_NAMES = frozenset(
    {"core", "worker", "main", "config", "errors", "security", "privacy", "realtime"}
)

__all__ = [
    "create_directories_and_files",
    "create_domain_doc_stub",
    "create_test_stubs",
    "main",
    "register_tach_boundaries",
    "scaffold_module",
    "validate_module_name",
]


def validate_module_name(name: str, root_dir: Path) -> None:
    if not _MODULE_NAME_REGEX.match(name):
        raise ValueError(
            f"Nome de módulo '{name}' inválido; esperado snake_case minúsculo "
            f"iniciado por letra (ex: prontuario, teleconsulta)."
        )

    if keyword.iskeyword(name) or name in _RESERVED_NAMES:
        raise ValueError(
            f"Nome de módulo '{name}' inválido; palavra reservada pelo sistema."
        )

    target_dir = root_dir / "src" / "modules" / name
    if target_dir.exists():
        raise FileExistsError(
            f"Módulo '{name}' já existe no diretório: '{target_dir}'."
        )


def create_directories_and_files(name: str, root_dir: Path) -> list[Path]:
    """Cria árvore de diretórios e arquivos __init__.py estruturais."""
    base = root_dir / "src" / "modules" / name
    created_files: list[Path] = []

    files_to_create: dict[Path, str] = {
        base / "__init__.py": f'"""Módulo {name} do MediSync Express."""\n',
        base / "composition.py": (
            f'"""Composition Root do módulo {name} (ADR-001 / ADR-009)."""\n\n'
            f"# Injeção de dependências e fábrica de serviços para {name}\n"
        ),
        base / "domain" / "__init__.py": (
            f'"""Camada de domínio do módulo {name}."""\n'
        ),
        base / "domain" / "models.py": (
            f'"""Modelos ricos e agregados do módulo {name}."""\n'
        ),
        base / "domain" / "exceptions.py": (
            f'"""Exceções canônicas de domínio do módulo {name}."""\n'
        ),
        base / "application" / "__init__.py": (
            f'"""Casos de uso e portas do módulo {name}."""\n'
        ),
        base / "application" / "dtos.py": (
            f'"""Commands e DTOs de aplicação do módulo {name}."""\n'
        ),
        base / "application" / "ports" / "__init__.py": (
            f'"""Portas abstratas (PEP 544) do módulo {name}."""\n'
        ),
        base / "application" / "services" / "__init__.py": (
            f'"""Serviços de aplicação do módulo {name}."""\n'
        ),
        base / "infrastructure" / "__init__.py": (
            f'"""Adaptadores de infraestrutura e persistência do módulo {name}."""\n'
        ),
        base / "infrastructure" / "adapters" / "__init__.py": (
            f'"""Adaptadores concretos do módulo {name}."""\n'
        ),
        base / "presentation" / "__init__.py": (
            f'"""Camada de apresentação (routers e schemas) do módulo {name}."""\n'
        ),
        base / "presentation" / "schemas.py": (
            f'"""Schemas Pydantic v2 (from_attributes=True) do módulo {name}."""\n'
        ),
        base / "presentation" / "dependencies.py": (
            f'"""Dependências FastAPI da apresentação do módulo {name}."""\n'
        ),
        base / "presentation" / "routers" / "__init__.py": (
            f'"""Agregação de rotas HTTP/WS do módulo {name} (ADR-001 §7.1)."""\n\n'
            f"from fastapi import APIRouter\n\n"
            f'http_router = APIRouter(prefix="/{name}", tags=["{name}"])\n'
            f'__all__ = ["http_router"]\n'
        ),
    }

    for path, content in files_to_create.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created_files.append(path)

    return created_files


def create_test_stubs(name: str, root_dir: Path) -> list[Path]:
    """Cria stubs de testes unitários espelho."""
    unit_tests_dir = root_dir / "tests" / "unit"
    unit_tests_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    service_test = unit_tests_dir / f"test_{name}_service.py"
    if not service_test.exists():
        service_test.write_text(
            f'"""Testes unitários para serviços do módulo {name}."""\n\n'
            f"import pytest\n"
            f"from tests.doubles import FakeAsyncSession\n\n"
            f"@pytest.mark.asyncio\n"
            f"async def test_{name}_service_initial_stub() -> None:\n"
            f'    """Substitua pelo primeiro teste TDD Red do serviço."""\n'
            f"    assert True\n",
            encoding="utf-8",
        )
        created.append(service_test)

    router_test = unit_tests_dir / f"test_{name}_router.py"
    if not router_test.exists():
        router_test.write_text(
            f'"""Testes unitários para rotas da apresentação do módulo {name}."""\n\n'
            f"import pytest\n\n"
            f"@pytest.mark.asyncio\n"
            f"async def test_{name}_router_initial_stub() -> None:\n"
            f'    """Substitua pelo teste de contrato de rota da apresentação."""\n'
            f"    assert True\n",
            encoding="utf-8",
        )
        created.append(router_test)

    return created


def create_domain_doc_stub(name: str, root_dir: Path) -> Path:
    """Cria documento Diátaxis do domínio no padrão de 5 seções obrigatórias."""
    domains_dir = root_dir / "docs" / "explanation" / "domains"
    domains_dir.mkdir(parents=True, exist_ok=True)
    doc_path = domains_dir / f"{name}-domain.md"

    if not doc_path.exists():
        title = name.replace("_", " ").title()
        content = (
            f"# Domínio: {title} ({name.upper()})\n\n"
            f"## 1. Visão Geral e Conceito\n"
            f"Descrição do bounded context de {title} no MediSync Express.\n\n"
            f"## 2. Regras de Negócio Canônicas\n"
            f"- **RN-{name[:3].upper()}-01**: Regra clínica canônica inicial.\n\n"
            f"## 3. Arquitetura e Portas Hexagonais\n"
            f"Estrutura de portas abstratas e adaptadores da camada de aplicação.\n\n"
            f"## 4. Contratos e Apresentação\n"
            f"Schemas Pydantic e agregação de rotas em `http_router`.\n\n"
            f"## 5. Rastreabilidade e Verificação\n"
            f"- Impl: `src/modules/{name}/presentation/routers/__init__.py`\n"
            f"- Spec: `docs/explanation/domains/{name}-domain.md`\n"
            f"- Teste: `tests/unit/test_{name}_service.py`\n"
        )
        doc_path.write_text(content, encoding="utf-8")

    return doc_path


def register_tach_boundaries(name: str, root_dir: Path) -> bool:
    """Injeta as 5 camadas hexagonais do módulo no tach.toml caso não existam."""
    tach_path = root_dir / "tach.toml"
    if not tach_path.exists():
        return False

    content = tach_path.read_text(encoding="utf-8")
    domain_module = f'path = "src.modules.{name}.domain"'
    if domain_module in content:
        return False

    module_blocks = (
        f"\n[[modules]]\n"
        f'path = "src.modules.{name}.domain"\n'
        f'depends_on = ["src.core"]\n'
        f"\n[[modules]]\n"
        f'path = "src.modules.{name}.application"\n'
        f'depends_on = ["src.core", "src.modules.{name}.domain"]\n'
        f"\n[[modules]]\n"
        f'path = "src.modules.{name}.infrastructure"\n'
        f"depends_on = [\n"
        f'    "src.core",\n'
        f'    "src.modules.{name}.application",\n'
        f'    "src.modules.{name}.domain",\n'
        f"]\n"
        f"\n[[modules]]\n"
        f'path = "src.modules.{name}.composition"\n'
        f"depends_on = [\n"
        f'    "src.core",\n'
        f'    "src.modules.{name}.application",\n'
        f'    "src.modules.{name}.domain",\n'
        f'    "src.modules.{name}.infrastructure",\n'
        f"]\n"
        f"\n[[modules]]\n"
        f'path = "src.modules.{name}.presentation"\n'
        f"depends_on = [\n"
        f'    "src.core",\n'
        f'    "src.modules.{name}.application",\n'
        f'    "src.modules.{name}.composition",\n'
        f"]\n"
    )

    tach_path.write_text(content.rstrip() + "\n" + module_blocks, encoding="utf-8")
    return True


def scaffold_module(name: str, root_dir: Path | None = None) -> None:
    """Orquestra a criação do módulo hexagonal."""
    root = root_dir or Path.cwd()
    validate_module_name(name, root)

    print(f"🚀 Criando scaffolding para módulo '{name}' em {root}...")
    files = create_directories_and_files(name, root)
    print(
        f"   ✅ {len(files)} arquivos de código e pacotes criados em src/modules/{name}"
    )

    test_files = create_test_stubs(name, root)
    print(f"   ✅ {len(test_files)} stubs de teste criados em tests/unit/")

    doc_file = create_domain_doc_stub(name, root)
    print(f"   ✅ Stub Diátaxis criado em {doc_file.relative_to(root)}")

    tach_registered = register_tach_boundaries(name, root)
    if tach_registered:
        print("   ✅ Camadas hexagonais registradas com sucesso no tach.toml")
    else:
        print("   ⚠️  tach.toml já possuía o módulo ou não foi encontrado.")

    print(f"\n🎉 Módulo '{name}' inicializado com sucesso!")
    print("Próximos passos recomendados:")
    print("  1. Inicie pelo ciclo TDD Red: escreva testes unitários em tests/unit/")
    print(f"  2. Adicione regras em docs/explanation/domains/{name}-domain.md")
    print("  3. Valide as fronteiras modulares com: just tach")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera estrutura física hexagonal para novo módulo no MediSync."
    )
    parser.add_argument("name", help="Nome do módulo em snake_case (ex: prontuario)")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Caminho raiz do repositório (padrão: diretório atual)",
    )
    args = parser.parse_args()

    try:
        scaffold_module(args.name, args.root)
    except Exception as err:
        print(f"❌ Erro ao gerar módulo: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
