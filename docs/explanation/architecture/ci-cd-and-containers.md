# CI/CD Strategy & Container Architecture

> Fundamentação arquitetural do pipeline paralelo de CI, isolamento de migrações e empacotamento multi-stage com Granian.

## Contexto

Consulte este documento para entender as decisões técnicas que guiam o ciclo de vida de Integração Contínua (CI) e a conteinerização no MediSync Express.

Para comandos operacionais de execução, veja `docs/how-to/dev-environment/run-docker.md`. Para a especificação exata de cada etapa e variáveis de ambiente, consulte `docs/reference/ci-cd/pipeline.md`.

## Conceito

### 1. Filosofia Fail-Fast e Paralelismo de Jobs

No pipeline do GitHub Actions (`.github/workflows/ci.yml`), as etapas de validação são distribuídas em três jobs paralelos:
* `code-quality`: Linters (`ruff`), checagem estrita de tipos (`basedpyright`) e auditoria modular (`tach`).
* `unit-tests`: Testes de domínio, modelos ricos e AST em memória com `pytest-xdist`.
* `docker-build`: Compilação da imagem OCI através do Docker Buildx com cache `type=gha`.

A execução paralela reduz o tempo de resposta (wall-clock time) para o desenvolvedor ao patamar do job mais lento, em vez de acumular tempo em uma fila sequencial. Além disso, fornece granularidade nos status checks do Pull Request, permitindo identificar imediatamente se uma quebra decorreu de violação arquitetural, erro de tipagem ou falha de empacotamento.

### 2. Por que Migrações não rodam no Fast CI

A pirâmide de testes do MediSync Express (detalhada em `docs/explanation/architecture/testing-strategy.md`) estabelece segregação estrita entre testes unitários e testes de integração:
* **Camada U (Unitários):** 100% em memória, zero Docker, zero banco relacional e zero I/O de rede. Executa em ~13s.
* **Camada I (Integração):** Valida sobre infraestrutura real (PostgreSQL com RLS, Valkey com scripts Lua, MinIO e LiveKit).

Executar migrações (`alembic upgrade head`) no Fast CI exigiria provisionar um contêiner de banco de dados e aplicar scripts DDL de inicialização (`scripts/postgres/01-init-extensions.sql`), o que violaria o princípio de testes unitários sem I/O e aumentaria o tempo de feedback do PR. As migrações possuem uma suíte exaustiva de validação no arquivo `tests/integration/test_migrations.py`, que valida criação de tabelas, triggers anti-adulteração e ciclos de rollback (`downgrade base`).

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


## Onde no código

- Impl: `.github/workflows/ci.yml:jobs`
- Impl: `Dockerfile:production`
- Prova viva: `tests/integration/test_migrations.py:test_downgrade_base_and_reupgrade_lifecycle`
- Spec: `docs/explanation/architecture/testing-strategy.md`
- Ver: `rg -n "name: CI" .github/workflows/ci.yml`
- Ver: `rg -n "USER appuser" Dockerfile`
- Ver: `rg -n "docker-build" justfile`

## Verificação

```bash
just docker-build
docker run --rm -d --name medisync-arch-test -p 8089:8080 -e PORT=8080 medisync:latest
sleep 2
docker ps --filter "name=medisync-arch-test"
docker stop medisync-arch-test
```

Esperado: contêiner sobe em segundo plano, executa como usuário não-root e encerra com código 0.

## Ver também

- [Run Docker Container](../../how-to/dev-environment/run-docker.md)
- [CI Pipeline & Docker Specification](../../reference/ci-cd/pipeline.md)
- [Testing Strategy](testing-strategy.md)
- [Architecture Overview](overview.md)
- [Setup Local](../../how-to/dev-environment/setup-local.md)
