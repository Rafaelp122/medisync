# Wire module dependencies (composition root)

> Como plugar adaptadores, compor dependências em módulos e auditar contra divergência arquitetural.

## Contexto

Cada módulo em `src/modules/` possui um Composition Root isolado em `composition.py` (ADR-001, ADR-009). Ele é o único arquivo do módulo autorizado a instanciar adaptadores de `infrastructure/` e conectá-los às portas de `application/ports/`.

Siga este guia sempre que:
1. Criar um novo módulo de domínio e precisar expor dependências para routers, workers ou outros módulos.
2. Adicionar um adaptador de infraestrutura alternativo (ex.: mock em memória vs driver real).
3. Auditar a base de código para garantir que serviços de aplicação e composition roots permaneçam desacoplados.

## Conceito

A fiação de dependências obedece a cinco regras canônicas de replicação e auditoria:

### 1. Passo a Passo de Replicação

1. **Defina a Porta Abstrata**: Crie a interface em `src/modules/<modulo>/application/ports/<nome>_port.py` utilizando `typing.Protocol` (PEP 544).
2. **Implemente os Adaptadores**: Crie as implementações concretas em `src/modules/<modulo>/infrastructure/adapters/`. Implemente tanto a versão real (ex.: Valkey/HTTP) quanto a versão em memória/fake para testes ultrarrápidos quando aplicável.
3. **Declare o Seletor Opcional**: Se o adaptador for intercambiável, adicione o seletor correspondente em `src/core/config.py` (dentro de `CommonSettings` com default seguro de desenvolvimento e ajuste em `TestSettings`).
4. **Componha a Fiação na `composition.py`**:
   - Injete as configurações via `get_settings()` ou `SettingsDep`.
   - **Proibido usar `global` ou variáveis mutáveis de módulo**. Resolva as instâncias pontualmente ou via injeção com escopo de sessão.
   - Forneça a dupla de fábricas canônicas:
     * `get_<nome>_service(...)`: Fábrica assíncrona consumida por routers FastAPI via `Depends()`.
     * `build_<nome>_service_for_session(...)`: Fábrica síncrona consumida por workers ARQ, scripts CLI e testes.
5. **Injete no Serviço via Construtor**: O serviço em `application/services/` deve receber suas portas, conexões e parâmetros primitivos exclusivamente via `__init__`. **Nunca importe `get_settings()` dentro de `application/services/`**.

### 2. Procedimento de Auditoria

Para auditar um módulo recém-criado ou modificado antes de abrir PR:

1. **Auditoria de Serviços Limpos**: Verifique se nenhum serviço importa `get_settings` ou `src.core.config`:
   ```bash
   rg "get_settings|from src\.core\.config" src/modules/*/application/services/
   ```
   *Esperado*: Nenhum match encontrado (exit code 1).

2. **Auditoria de Composition Roots Sem Globais**: Verifique se nenhum `composition.py` usa declarações `global`:
   ```bash
   rg "global " src/modules/*/composition.py
   ```
   *Esperado*: Nenhum match encontrado (exit code 1).

3. **Auditoria de Routers Finos**: Verifique se nenhum router instancia serviços diretamente:
   ```bash
   uv run pytest tests/architecture/test_routers_are_thin.py --no-cov -q
   ```
   *Esperado*: Todos os testes AST aprovados.

4. **Auditoria Automatizada Completa de Composição**:
   ```bash
   uv run pytest tests/architecture/test_services_and_composition.py --no-cov -q
   ```
   *Esperado*: Todos os testes AST aprovados.

## Onde no código (só links)

- Impl config profiles: `src/core/config.py:CommonSettings`
- Impl composition auth: `src/modules/auth/composition.py:get_auth_service`
- Impl composition triage: `src/modules/triage/composition.py:get_triage_service`
- Impl composition consultation: `src/modules/consultation/composition.py:get_pep_service`
- Prova viva wiring: `tests/unit/test_composition_wiring.py:test_auth_rate_limiter_resolution`
- Prova viva arquitetura: `tests/architecture/test_services_and_composition.py:test_services_do_not_import_config_or_get_settings`
- Spec de governança: `tach.toml`

Ver:

```bash
rg -n "build_.*_for_session|get_.*_service" src/modules/auth/composition.py
```

Expected: Fábricas de injeção assíncronas e síncronas declaradas.

```bash
rg -n "def test_.*_resolution" tests/unit/test_composition_wiring.py
```

Expected: Testes unitários cobrindo a alternância dinâmica de backends.

## Verificação

Run (guardas de arquitetura e fiação):

```bash
uv run pytest tests/architecture/ -v --no-cov
uv run pytest tests/unit/test_composition_wiring.py -v --no-cov
```

Expected: 8 testes de arquitetura e 5 testes de fiação aprovados com código de retorno 0.

Run (validação de fronteiras modulares):

```bash
just tach
```

Expected: `All modules validated!`, exit 0.

## Ver também

- [Create module endpoint](create-module-endpoint.md)
- [Composition Root e Injeção de Dependências](../../explanation/concepts/composition-root-and-dependencies.md)
- [Environment Variables](../../reference/environment/variables.md)
- [Write tests](write-tests.md)
- [ADR-001](../../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)
- [ADR-009](../../adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md)
