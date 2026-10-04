# MediSync Express — Guia do Desenvolvedor de IA (AGENTS.md)

Este documento contém as instruções mandatórias para qualquer agente de IA ou desenvolvedor atuando neste repositório.

---

## 1. Comandos e Tooling

* **Gerenciador de Pacotes:** `uv`. Nunca use `pip install` global.
* **Automação:** Sempre utilize os comandos do `justfile`:
  * `just check` — Executa o portão de qualidade completo (fmt, lint, typecheck, tach, test).
  * `just fmt` — Formata o código com `ruff`.
  * `just lint` — Executa lint com autofix seguro (`ruff check . --fix`).
  * `just typecheck` — Executa checagem estrita de tipos com `basedpyright`.
  * `just tach` — Valida as fronteiras modulares com `tach check`.
  * `just test` — Executa testes com medição de cobertura (`pytest`).
  * `just test-fast` — Executa testes rápidos em paralelo (`pytest -n auto --no-cov`).

---

## 2. Princípios Arquiteturais Pétreos (ADR-001)

1. **Hexagonal Pragmático sem Mapper Hell (ADR-001 / ADR-008):**
   * Entidades persistidas com SQLAlchemy 2.0 (`Mapped[...]`) são **modelos ricos** e residem no domínio do próprio módulo.
   * Encapsulam regras clínicas, validações e transições de estado.
   * **Proibido:** Criar DTOs espelho duplicados com conversores manuais (`to_domain`/`to_orm` ou `dto_to_schema`/`schema_to_dto`).
   * **Entradas (Requests):** Se os dados vêm 100% do corpo JSON, utilize o schema Pydantic (`frozen=True`) diretamente como entrada do Service. Use `@dataclass(frozen=True)` com sufixo `Command` em `application/dtos.py` apenas quando for necessário agregar dados de múltiplas origens (Path Params, Headers de Tenant, IP, etc.).
   * **Saídas (Responses):** Schemas de resposta devem usar `model_config = ConfigDict(from_attributes=True)` e conversão via `ResponseSchema.model_validate(objeto)`. Proibido mapeamento manual campo a campo.
   * **Organização Física:** Schemas Pydantic residem exclusivamente em `src/modules/<modulo>/presentation/schemas.py`. Commands/DTOs residem em `src/modules/<modulo>/application/dtos.py`.
2. **Comunicação Inter-Módulos:**
   * Os módulos em `src/modules/*` são independentes e fechados.
   * Comunicação síncrona ocorre exclusivamente via portas abstratas (`typing.Protocol` do PEP 544) e DTOs imutáveis (`@dataclass(frozen=True)` ou Pydantic v2).
   * **Proibido:** Importar modelos internos, tabelas ou repositórios de outro módulo.
   * Toda violação modular é bloqueada pelo `tach check`.
3. **Tipagem Estrita:**
   * O código deve passar em `basedpyright` com `typeCheckingMode = "strict"`.
   * Evite `Any`. Use tipos genéricos, `Union`, `Literal` ou `Protocol`.

---

## 3. Catálogo de Skills do Projeto

Consulte e utilize as skills especializadas localizadas em `.agents/skills/`:
* [`.agents/skills/fastapi`](.agents/skills/fastapi/SKILL.md): Boas práticas com FastAPI, injeção de dependências, routers e Pydantic v2.
* [`.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review`](.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review/SKILL.md): Padrões de queries assíncronas no SQLAlchemy 2.0, migrations idempotentes e modelagem relacional.
* [`.agents/skills/valkey`](.agents/skills/valkey/SKILL.md): Comandos atômicos, Sorted Sets (ZSET), scripts Lua e caching de alta performance.

---

## 4. Definição de Pronto (DoD)

Antes de finalizar qualquer tarefa ou abrir PR:
- [ ] O código adere aos padrões do Hexagonal Pragmático.
- [ ] Novos testes foram adicionados (unitários ou integração).
- [ ] `just check` foi executado e passou com código de retorno 0.
