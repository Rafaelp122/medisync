# CI Pipeline & Docker Specification

> Especificação técnica factual dos jobs de integração contínua no GitHub Actions e contratos do contêiner Docker.

## Contexto

Consulte este documento para obter a referência exata dos comandos, gatilhos, variáveis de ambiente e estágios do pipeline de CI/CD do MediSync Express localizado em `.github/workflows/ci.yml`.

Para instruções passo a passo de como rodar o contêiner, consulte `docs/how-to/dev-environment/run-docker.md`. Para a motivação das escolhas arquiteturais, consulte `docs/explanation/architecture/ci-cd-and-containers.md`.

## Conceito

### Matriz de Jobs do CI (`.github/workflows/ci.yml`)

O pipeline é acionado nos eventos `push` e `pull_request` direcionados à branch `main`. A concorrência é configurada com `cancel-in-progress: true` para otimizar consumo de runners.

| Job | Escopo / Responsabilidade | Comandos Executados | Dependências Externas |
| :--- | :--- | :--- | :--- |
| `code-quality` | Validação estática, formatação, tipos e fronteiras | `uv run ruff format --check .`<br>`uv run ruff check .`<br>`uv run basedpyright`<br>`uv run tach check` | Nenhuma (em memória) |
| `unit-tests` | Regras clínicas, modelos ricos e AST routers | `uv run pytest tests/unit tests/architecture -n auto --cov=src` | Nenhuma (em memória) |
| `docker-build` | Validação de empacotamento OCI multi-stage | `docker buildx build --target production` (cache `gha`) | Docker Buildx |

### Estágios do `Dockerfile`

O arquivo `Dockerfile` define quatro estágios sequenciais e reutilizáveis:

| Estágio | Imagem Base | Finalidade | Usuário | Porta |
| :--- | :--- | :--- | :--- | :--- |
| `base` | `python:3.14-slim` | Runtime comum, deps C de sistema (`libpq5`, `curl`) | `root` | - |
| `builder` | `base` + `ghcr.io/astral-sh/uv:latest` | Compila venv de produção em `/opt/venv` sem dev | `root` | - |
| `development` | `builder` | Venv completo com deps dev e granian reload | `root` | `8000` |
| `production` | `base` | Imagem final mínima com bytecode pré-compilado | `appuser` (1000) | `8080` |

### Variáveis de Ambiente do Servidor ASGI (Granian)

A imagem de produção executa o servidor Granian sobre `src.main:app` com suporte às seguintes variáveis:

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `PORT` | `8080` | Porta TCP escutada pelo servidor Granian |
| `GRANIAN_WORKERS` | `2` | Número de processos trabalhadores paralelos |
| `GRANIAN_HTTP` | `auto` | Versão do protocolo HTTP (HTTP/1.1 e HTTP/2) |
| `PYTHONOPTIMIZE` | `1` | Ativa otimização de bytecode do interpretador CPython |
| `PYTHONPATH` | `/app` | Raiz de importação dos módulos da aplicação |

### Estratégia de Cache e Eficiência no CI

O pipeline de CI adota dois mecanismos de cache para minimizar tempo de execução:
1. **Cache de Dependências uv (`astral-sh/setup-uv@v5`):**
   * Parâmetro: `enable-cache: true`.
   * Chave de cache: hash do arquivo `uv.lock`.
   * Restaura o diretório de cache do `uv` em aproximadamente 2 segundos em cada job independente.
2. **Cache de Camadas Docker (`docker/build-push-action@v6`):**
   * Backend de cache: `type=gha` (GitHub Actions Cache API).
   * Modo: `mode=max` (armazena todas as camadas intermediárias dos estágios `base` e `builder`).
   * Permite reuso direto das camadas compilaras em builds subsequentes de Pull Requests.

### Concorrência e Cancelamento Automático

O workflow define a política de cancelamento preventivo:
* Grupo: `${{ github.workflow }}-${{ github.ref }}`.
* `cancel-in-progress: true`: Quando novos commits são enviados para um Pull Request aberto, execuções anteriores ainda em andamento são canceladas imediatamente para economizar minutos de runner.

## Onde no código

- Impl: `.github/workflows/ci.yml:jobs`
- Impl: `Dockerfile:production`
- Spec: `pyproject.toml:project.dependencies`
- Prova viva: `.github/workflows/ci.yml:docker-build`
- Ver: `rg -n "runs-on:" .github/workflows/ci.yml`
- Ver: `rg -n "GRANIAN_WORKERS" Dockerfile`

## Verificação

```bash
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run tach check
just docker-build
```

Esperado: todas as checagens estáticas retornam código 0; build Docker conclui gerando tag `medisync:latest`.

## Ver também

- [Run Docker Container](../../how-to/dev-environment/run-docker.md)
- [Testing Strategy](../../explanation/architecture/testing-strategy.md)
- [CI/CD Strategy & Container Architecture](../../explanation/architecture/ci-cd-and-containers.md)
- [Environment Variables](../environment/variables.md)
