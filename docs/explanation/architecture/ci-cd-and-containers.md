# CI/CD Strategy & Container Architecture

> Fundamentação arquitetural do pipeline paralelo de CI, isolamento de migrações e empacotamento multi-stage com Granian.

## Contexto

Consulte este documento para entender as decisões técnicas que guiam o ciclo de vida de Integração Contínua (CI) e a conteinerização no MediSync Express.

Para comandos operacionais de execução, veja `docs/how-to/dev-environment/run-docker.md`. Para a especificação exata de cada etapa e variáveis de ambiente, consulte `docs/reference/ci-cd/pipeline.md`.

## Conceito

### 1. Filosofia Fail-Fast, Filtragem de Caminhos e Paralelismo de Jobs

No pipeline do GitHub Actions (`.github/workflows/ci.yml`), as etapas de validação são orientadas por detecção seletiva de caminhos (`dorny/paths-filter@v3`) e distribuídas em jobs paralelos com Fail-Fast estrito:
* `detect-changes`: Mapeia alterações entre `backend`, `frontend` e `docs`, ignorando execuções redundantes.
* `code-quality`: Linters (`ruff`), checagem estrita de tipos (`basedpyright`), auditoria modular (`tach`), auditoria de Diátaxis (`docs_check.py`) e diretrizes Clean Code / Web Guidelines (`audit_ai_clean_code.py` e `audit_frontend_guidelines.py`) em memória.
* `database-migrations`: Executa sobre contêiner de serviço PostgreSQL 17 isolado, aplicando migrações (`alembic upgrade head`) e auditando drift de esquemas (`alembic check`).
* `unit-tests`: Testes de domínio, modelos ricos e AST em memória com `pytest-xdist`.
* `frontend-quality` & `frontend-tests`: Validação de contratos OpenAPI tipados (Hey API), checagem de tipos e testes de tela (Vitest + MSW v2).
* `frontend-e2e`: Testes ponta a ponta (Playwright + Axe-core WCAG 2.1 AA) com upload automático de `playwright-report` em falha.
* `docker-build`: Compilação da imagem OCI via Docker Buildx e Smoke Test HTTP real em `/healthz`.

A execução paralela reduz o tempo de resposta (wall-clock time) para o desenvolvedor ao patamar do job mais lento, em vez de acumular tempo em uma fila sequencial. Além disso, fornece granularidade nos status checks do Pull Request, permitindo identificar imediatamente se uma quebra decorreu de violação arquitetural, erro de tipagem, drift de migrações ou falha de empacotamento.

### 2. Validação de Migrações e Detecção de Drift no CI

Para garantir que nenhuma alteração em entidades do SQLAlchemy seja enviada sem sua respectiva migração do Alembic:
* **Job Dedicado de Migração:** O job `database-migrations` conecta-se a um serviço PostgreSQL 17 temporário e executa `alembic upgrade head` seguido por `alembic check`.
* **Detecção Automática de Drift:** Caso um desenvolvedor modifique um modelo declarativo em `src/modules/*/domain/models/` e esqueça de gerar o arquivo de migração, o comando `alembic check` detecta a divergência e falha a esteira preventivamente antes do merge.
* **Isolamento da Camada Unitária:** Os testes unitários rápidos (`unit-tests`) continuam 100% em memória (zero Docker e zero I/O de rede), preservando o loop rápido de desenvolvimento. As migrações possuem validação contínua de rollback (`downgrade base`) na suíte de integração (`tests/integration/test_migrations.py`).

### 3. Empacotamento Multi-Stage com `uv`

A imagem Docker adota o padrão multi-stage para desacoplar ferramentas de compilação do artefato executável final:
* **Isolamento de Compiladores:** Dependências com extensões C (como `psycopg`, `cryptography` e `pillow`) requerem compiladores C (`gcc`, `build-essential`, `libpq-dev`). Essas ferramentas ficam restritas ao estágio intermediário `builder` e são descartadas na imagem `production`.
* **Gerenciamento Determinístico via `uv`:** O binário estático do `uv` é importado de sua imagem oficial e gera o ambiente virtual `/opt/venv` a partir do `uv.lock` com flags `--frozen --no-dev`.
* **Otimização de Bytecode:** O comando `python -m compileall -q .` compila os arquivos Python em `.pyc` durante o build, eliminando custo de compilação dinâmica no boot da aplicação.

### 4. Servidor ASGI Granian e Usuário Não-Root

O MediSync Express utiliza o Granian como servidor de aplicação ASGI:
* **Throughput Assíncrono:** Construído em Rust sobre o Hyper, o Granian oferece alta taxa de requisições por segundo e baixo overhead de memória, ideal para a alta concorrência médica exigida no PA Digital.
* **Modelo ASGI vs WSGI:** No modo ASGI, o Granian opera diretamente com o loop de eventos assíncrono do Python (`anyio` / `asyncio`), sem necessidade de pools de threads bloqueantes (`blocking-threads`). O escalonamento horizontal ocorre via múltiplos processos (`workers`) gerenciados pelo supervisor do Granian.
* **Segurança e Conformidade Clínica:** A imagem de produção não executa como `root`. O usuário não-privilegiado `appuser` (UID 1000) possui permissões restritas ao diretório `/app`, mitigando riscos de escape de contêiner em ambientes Kubernetes e Cloud Run.
* **Probes de Inicialização e Liveness:** O servidor inicia imediatamente sem overhead de compilação em runtime, permitindo que orquestradores (como Google Cloud Run) atendam probes de startup em menos de 1 segundo através do endpoint `/health`.

### 5. Isolamento de Contexto e Proteção de Segredos (`.dockerignore`)

Em conformidade com a LGPD e normas do CFM para dados clínicos sensíveis, o arquivo `.dockerignore` impede que artefatos locais vazem para a imagem:
* **Bloqueio de Variáveis Locais:** Arquivos `.env` e chaves temporárias são explicitamente excluídos do contexto enviado ao Docker Daemon.
* **Eliminação de Resíduos de Teste:** Diretórios `.pytest_cache`, `.coverage` e `.venv` são ignorados, garantindo que o estágio `builder` compile dependências limpas e reprodutíveis a partir do `uv.lock`.

### 6. Estratégia de DevSecOps e SAST em Camadas (ADR-010)

O MediSync Express adota uma estratégia de segurança em profundidade no ciclo de desenvolvimento (SDLC) estruturada em três camadas desacopladas:
1. **Firewall Local & Pre-Commit:** Verificação opcional no commit via `.pre-commit-config.yaml` e comando local `just scan-secrets`, executando o Gitleaks com allowlists estruturadas (`.gitleaks.toml` e `.gitleaksignore`) para proteger chaves e certificados de saúde.
2. **Fast CI de Pull Request (<30s):** O workflow `.github/workflows/secret-scanning.yml` executa o Gitleaks em paralelo aos jobs de lint, tipos e testes unitários em memória. Testes com I/O pesado ou contêineres reais não são executados neste portão síncrono.
3. **Deep SAST Assíncrono (CodeQL):** O workflow `.github/workflows/codeql.yml` realiza rastreamento profundo de fluxo de dados (*taint analysis*) em Python 3.12, acionado em pushes para a `main`, schedule semanal e PRs que mutacionam arquivos em `src/`, sem onerar o tempo de resposta do Fast CI.

### 7. Estratégia de Versionamento Semântico Automatizado (Commitizen & SemVer)

A rastreabilidade de versões no MediSync Express é tratada como requisito de governança clínica e conformidade regulatória (CFM e ANVISA). Para assegurar auditabilidade estrita sem fricção humana:

1. **Commitizen Nativo em Python:** Em vez de introduzir ecossistemas Node.js/npm no pipeline exclusivamente para release semântico, o projeto adota o `commitizen-tools` executado diretamente no ambiente Python com `uv`.
2. **Prevenção de Loops Recursivos no CI:** O workflow `.github/workflows/release.yml` monitora pushes na branch `main`. A cláusula condicional de job ignora commits iniciados por `bump:` ou `chore(release):`, prevenindo que a própria criação de tag e changelog dispare novos ciclos infinitos de release.
3. **Sincronização Atômica Multiarquivo (`.cz.toml`):** A cada bump, o Commitizen propaga simultaneamente o número de versão para:
   - `pyproject.toml` (metadados do pacote Python);
   - `src/core/config.py` (constante `APP_VERSION`, exposta publicamente no `/healthz` para checagem de integridade do cluster);
   - `CHANGELOG.md` (registro histórico incremental agrupado por `Feat`, `Fix` e `Refactor`).
4. **Governança de Fase Pré-1.0:** A diretiva `major_version_zero = true` no `.cz.toml` orienta o cálculo SemVer durante a fase de validação e homologação, permitindo evolução ágil sem inflar prematuramente a versão maior antes da maturidade de produção.


## Onde no código

- Impl: `.github/workflows/ci.yml:jobs`
- Impl: `.github/workflows/release.yml:jobs`
- Impl: `Dockerfile:production`
- Config: `.cz.toml`
- Versão: `src/core/config.py:APP_VERSION`
- Prova viva: `tests/integration/test_migrations.py:test_downgrade_base_and_reupgrade_lifecycle`
- Spec: `docs/explanation/architecture/testing-strategy.md`
- Ver: `rg -n "name: CI" .github/workflows/ci.yml`
- Ver: `rg -n "USER appuser" Dockerfile`
- Ver: `rg -n "smoke-docker" justfile`
- Ver: `rg -n "check-migrations" justfile`

## Verificação

```bash
just check-migrations
just smoke-docker
```

Esperado: checagem de migrações confirma ausência de drift e o contêiner de produção sobe, executa como usuário não-root e valida a resposta HTTP 200 em `/healthz`.

## Ver também

- [ADR-010: Estratégia de DevSecOps](../../adrs/ADR-010-Estrategia-DevSecOps-Defesa-em-Profundidade-de-Segredos-e-SAST.md)
- [Run Docker Container](../../how-to/dev-environment/run-docker.md)
- [Release e Versionamento Semântico](../../how-to/dev-environment/release-and-versioning.md)
- [CI Pipeline & Docker Specification](../../reference/ci-cd/pipeline.md)
- [Testing Strategy](testing-strategy.md)
- [Architecture Overview](overview.md)
- [Setup Local](../../how-to/dev-environment/setup-local.md)

