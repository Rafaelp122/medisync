# MediSync Express — Guia do Desenvolvedor de IA (AGENTS.md)

Este documento contém as instruções mandatórias para qualquer agente de IA ou desenvolvedor atuando neste repositório.

---

## 1. Comandos e Tooling

* **Gerenciador de Pacotes:** `uv`. Nunca use `pip install` global.
* **Automação:** Sempre utilize os comandos do `justfile`:
  * `just install` — Sincroniza ambiente e dependências com `uv` (`uv sync`).
  * `just setup-dev` — Inicializa o ambiente de desenvolvimento completo (infra Docker, deps, migrações e validação rápida).
  * `just check` — Executa o portão de qualidade completo e unificado com Fail-Fast estrito (scan-secrets, docs-check, audit-ai-code, fmt, lint, typecheck, tach, test-unit, test-integration).
  * `just check-fast` — Executa a validação rápida completa em memória (zero Docker: scan-secrets, docs-check, audit-ai-code, fmt, lint, typecheck, tach, test-fast).
  * `just fmt` — Formata o código com `ruff`.
  * `just lint` — Executa lint com autofix seguro (`ruff check . --fix`).
  * `just typecheck` — Executa checagem estrita de tipos com `basedpyright`.
  * `just tach` — Valida as fronteiras modulares com `tach check`.
  * `just test-fast` — Executa testes rápidos em paralelo (100% em memória, zero Docker: `pytest tests/unit tests/architecture -n auto --no-cov`).
  * `just test-unit` — Executa testes unitários com cobertura (`pytest tests/unit tests/architecture --cov=src`).
  * `just test-integration` — Executa testes de integração sobre infraestrutura real (`pytest tests/integration`).
  * `just test` — Executa a suíte de testes completa com cobertura consolidada.
  * `just docs-check` — Valida links `src/docs`, referências relativas e proíbe código colado nos docs.
  * `just audit-ai-code` — Audita o código sob os princípios de Clean Code para Agentes de IA.
  * `just scaffold-module <nome>` — Cria esqueleto físico hexagonal para novo módulo e registra no `tach.toml`.
  * `just scan-secrets` — Audita o repositório com Gitleaks (ADR-010) para prevenir vazamento de credenciais.
  * `just bump-check` — Simula o próximo bump de versão semântica e changelog via Commitizen.


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
4. **Transação + Router fino (ADR-001 §6-§7):**
   * Service commita, um por caso de uso (`await session.commit()` no fim do método público que persiste; helpers/policies nunca commitam).
   * Router nunca importa `sqlalchemy`/`infrastructure`/`domain.models`, nunca chama `.commit()/.refresh()/text()/select()`, nunca instancia `*Service(` (usa `*Dep` da `composition.py`).
   * `HTTPException` só em `presentation/dependencies.py` (ex.: `exigir_rate_limit` → 429); routers importam de lá. Erros de domínio via `src/core/errors.py` (`NotFoundError`, `ForbiddenError`, …).
   * Guardas: `tach check` (Stage B camadas + composition) + `tests/architecture/test_routers_are_thin.py` (AST) devem passar.
5. **Composition Root Enxuto e Agregação de Rotas (ADR-001 §7.1 / Issue #68):**
   * `src/main.py` é composition root enxuto: proibido importar `modules/*/infrastructure` (guard AST `tests/architecture/test_main_composition_root.py`).
   * Cada módulo agrega suas rotas em `src/modules/<modulo>/presentation/routers/__init__.py` exportando `http_router` (e `ws_router`). `main.py` inclui apenas 1 router HTTP por módulo sob `/api/v1`.
   * Endpoint de saúde `/healthz` reside em `src/core/health_router.py` sob o guard de routers finos e versão via `Settings.APP_VERSION`.
   * Ciclo de vida (`lifespan`) delega inicializações para hooks assíncronos nos composition roots dos módulos (ex: `queue.composition.on_startup`).
6. **Configurações Desacopladas por Perfil (ADR-009):**
   * Services e domínio nunca importam `get_settings()` ou `src.core.config`.
   * Dependências de ambiente são resolvidas exclusivamente nas composition roots (`composition.py`) e injetadas como tipos primitivos ou ports no service (guard AST `tests/architecture/test_services_and_composition.py`).
7. **Governança de Documentação Diátaxis (ADR-001 / Padrão Atômico-Denso):**
   * Toda nova feature, regra de negócio ou endpoint deve atualizar a documentação no mesmo PR: 1 conceito por arquivo (80–250 linhas), template obrigatório de 5 seções, zero código colado >5 linhas (usar `path:símbolo` + `rg`).
   * Novo `.env` $\to$ atualizar `docs/reference/environment/variables.md`; novo erro $\to$ `docs/reference/api/error-envelope.md`.
8. **Clean Code para Agentes de IA & Navegabilidade Semântica:**
   * **Nomes Únicos e 'Greppáveis' (<5 matches no `rg`):** Símbolos públicos (classes, métodos de serviço, ports, exceptions) devem ter nomes distintivos e rastreáveis. Proibido nomes genéricos como `data`, `handler`, `Manager`, `process()`, `execute()`.
   * **Exceções com Contexto do Valor Ofensivo (*Offending Value + Expected Shape*):** Exceções de domínio e validações devem sempre interpolar o valor recebido e o valor esperado (ex.: `raise StatusInvalidoError(f"Status '{status}' inválido; esperados: {sorted(StatusAtendimento)}")`), viabilizando diagnóstico instantâneo no traceback.
   * **Early Returns e Aninhamento Raso (Max 2 níveis):** Guard clauses imediatas no topo de funções e métodos. Proibido aninhamento profundo (`if/else` encadeados dentro de loops). Limite máximo de 2 níveis de estruturas de controle por função.
   * **Docstrings Atômicas de Proveniência (WHY, not WHAT):** Docstrings atômicas de 3 a 5 linhas em métodos públicos de services e modelos clínicos com regras de negócio, referenciando explicitamente a regra canônica (`RN01-RN07`, `RF-01-RF-10`, `ADR-xxx`, normas CFM/LGPD) e o link do documento em `docs/`. Proibido repetir `Args:` e `Returns:` já tipados na assinatura. Código aponta para doc (`Regras: docs/...`), doc aponta para código (`Impl: src/...:simbolo`).
   * **Fakes Nomeados sobre Mocks Inline Anônimos:** Testes unitários devem priorizar Fakes em memória tipados (`MemoryTokenRevocation`, `MemoryQueuePort`) em vez de mocks anônimos (`MagicMock()`, `patch()`), garantindo checagem de tipos estrita (`basedpyright`) nos testes.
   * **Menor Alteração Completa & YAGNI Radical (The Smallest Complete Change):** O melhor código é aquele que não precisa ser escrito. Resolva o problema por completo com a menor quantidade de código novo legível. Antes de criar código, siga a escada de decisão: (1) Precisa existir? (2) Já existe no codebase (helper, fake, port)? Reutilize; (3) A biblioteca padrão ou linguagem já faz? Use-a; (4) Uma dependência já instalada resolve? Use-a sem adicionar novos pacotes; (5) Só então escreva novo código. Proibido adicionar camadas, builders, wrappers, tipos intermediários (Mapper Hell) ou opções que ninguém pediu.
   * **Zero Speculative Code (Never Code Around Ambiguity):** Proibido criar código defensivo, opções não solicitadas, fallbacks especulativos ou rotas alternativas (`@router.post(...)` duplicados) para acomodar ambiguidades de narrativa ou termos divergentes. Toda ação possui exatamente 1 contrato canônico RESTful/WS definido na Issue. Divergências terminológicas devem ser resolvidas unificando a documentação viva (`docs/`) antes do código, nunca codificando ao redor da ambiguidade.
   * **Grep Every Caller (Proteção contra Regressão Silenciosa):** Uma mudança pode quebrar código que ela não toca diretamente. Antes de alterar a assinatura, retorno ou comportamento de qualquer função, método de serviço, DTO ou modelo, execute obrigatoriamente uma busca global (`grep_search`) por todos os chamadores no repositório e ajuste-os no mesmo ciclo.

---

## 3. Catálogo de Skills do Projeto

Consulte e utilize as skills especializadas localizadas em `.agents/skills/`:
* [`.agents/skills/medisync-issue-creator`](.agents/skills/medisync-issue-creator/SKILL.md): Formalização de necessidades e gestão de escopo em dois eixos ortogonais (Diagnóstico & Impacto vs YAGNI & Guardrails) via subagentes paralelos. Transforma ideias, bugs e débitos em issues canônicas blindadas contra scope creep antes do planejamento.
* [`.agents/skills/medisync-issue-planner`](.agents/skills/medisync-issue-planner/SKILL.md): Planejamento técnico em dois eixos (Standards & Arquitetura vs Spec & Diátaxis), fatiamento TDD Inside-Out e aplicação da Menor Alteração Completa.
* [`.agents/skills/medisync-pr-review`](.agents/skills/medisync-pr-review/SKILL.md): Revisão hostil independente do PR/diff em sessão limpa (Zero-Context / Segregação de Funções) em dois eixos (Standards vs Spec) com inventário mecânico de rotas via shell e achados concretos em 4 partes.
* [`.agents/skills/medisync-module-audit`](.agents/skills/medisync-module-audit/SKILL.md): Auditoria cirúrgica e aprofundada de um módulo hexagonal (bounded context) em repouso: integridade clínica, routers finos, conformidade Diátaxis/ADRs, concorrência e oportunidades de deleção lean.
* [`.agents/skills/fastapi`](.agents/skills/fastapi/SKILL.md): Boas práticas com FastAPI, injeção de dependências, routers e Pydantic v2.
* [`.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review`](.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review/SKILL.md): Padrões de queries assíncronas no SQLAlchemy 2.0, migrations idempotentes e modelagem relacional.
* [`.agents/skills/valkey`](.agents/skills/valkey/SKILL.md): Comandos atômicos, Sorted Sets (ZSET), scripts Lua e caching de alta performance.
* [`.agents/skills/codebase-design`](.agents/skills/codebase-design/SKILL.md): Design de módulos profundos, interfaces coesas e encapsulamento.

---

## 4. Definição de Pronto (DoD)

Antes de finalizar qualquer tarefa ou abrir PR:
- [ ] O código adere aos padrões do Hexagonal Pragmático.
- [ ] Novos testes foram adicionados (unitários ou integração).
- [ ] Exceções levantadas contêm o valor ofensivo e a restrição esperada.
- [ ] Aninhamento de controle de fluxo respeita o teto de 2 níveis.
- [ ] Docstrings de regras de negócio contêm links atômicos de proveniência para `docs/`.
- [ ] Documentação correspondente atualizada sob o padrão Diátaxis (sem código colado >5 linhas).
- [ ] `just check` (ou `just check-fast` em validações locais sem Docker) foi executado e passou com código de retorno 0 (cobrindo segredos, documentação, clean code, linters, tipos, fronteiras modulares e testes).
