# Run Docker Container

> Guia operacional para compilar e executar localmente o contêiner do MediSync Express via Docker e Justfile.

## Contexto

Consulte este guia sempre que precisar validar o empacotamento da aplicação em contêiner OCI, executar a aplicação sem dependência do ambiente virtual da máquina hospedeira ou simular o comportamento de runtime do servidor Granian ASGI em produção antes de abrir um Pull Request.

Para instruções de configuração do ambiente nativo com `uv`, consulte `docs/how-to/dev-environment/setup-local.md`.

## Conceito

O MediSync adota um `Dockerfile` multi-stage com quatro estágios independentes:
1. `base`: Contém Python 3.14-slim, bibliotecas de sistema C mínimas (`libpq5`, `curl`, `ca-certificates`) e variáveis globais de runtime.
2. `builder`: Instala o gerenciador `uv` a partir da imagem oficial e compila o ambiente virtual de produção em `/opt/venv` sem dependências de teste.
3. `development`: Constrói o ambiente com hot-reload ativo (`--reload`) e dependências completas para desenvolvimento local.
4. `production`: Gera a imagem enxuta de produção, executa como usuário não-root `appuser` (UID 1000) e sobe o servidor ASGI Granian escutando na porta 8080.

A automação local via `justfile` encapsula os comandos do Docker Engine para simplificar o fluxo de trabalho do desenvolvedor.

### Fluxo de execução de desenvolvimento
Para subir o contêiner em modo de desenvolvimento local:
```bash
just docker-build-dev
docker run --rm -p 8000:8000 -v $(pwd):/app medisync:dev
```

### Fluxo de execução de produção
Para testar a imagem final de produção idêntica à implantada no Cloud Run:
```bash
just docker-build
docker run --rm -d --name medisync-app -p 8080:8080 -e PORT=8080 medisync:latest
```

Para verificar o processo e logs do contêiner:
```bash
docker logs medisync-app
docker stop medisync-app
```

### Inspeção interativa e operações em contêiner
Para depurar ou executar tarefas dentro do contêiner `backend` em execução (`just up`):
```bash
just docker-shell
```
Dentro ou fora da sessão interativa, as tarefas de banco e testes em contêiner possuem receitas dedicadas:
- Migrações: `just docker-migrate`
- Seed de desenvolvimento: `just docker-seed`
- Testes unitários: `just docker-test`
- Acompanhamento de logs: `just logs backend`

### Resolução de problemas comuns

1. **Porta em uso (`bind: address already in use` / `os error 98`):**
   * O comando `just up` inicia a topologia completa incluindo o contêiner `backend` na porta 8000.
   * Para desenvolvimento local com `just backend-dev` ou `just dev`, suba apenas serviços essenciais com `just up-infra`.
   * Caso o contêiner `backend` já esteja ativo: pare-o com `docker compose stop backend`.
2. **Permissão de arquivos com usuário não-root:**
   * A imagem de produção roda sob UID 1000 (`appuser`). Ao mapear volumes locais para produção, garanta que os arquivos possuam permissão de leitura para o UID 1000.
3. **Erros de importação no boot:**
   * Se um módulo não for encontrado na imagem de produção, confirme se a biblioteca correspondente foi adicionada em `dependencies` no `pyproject.toml` (e não apenas no grupo `dev`).

## Onde no código

- Impl: `Dockerfile:production`
- Spec: `justfile:docker-build`
- Spec: `justfile:docker-migrate`
- Spec: `justfile:docker-shell`
- Prova viva: `.github/workflows/ci.yml:docker-build`
- Ver: `rg -n "docker-build" justfile`
- Ver: `rg -n "FROM.*production" Dockerfile`

## Verificação

```bash
just docker-build
docker inspect --format='{{.Config.User}}' medisync:latest
docker inspect --format='{{.Config.ExposedPorts}}' medisync:latest
```

Esperado: compilação finalizada com sucesso, usuário reportado como `appuser` e porta exposta `8080/tcp`.

## Ver também

- [Setup local](setup-local.md)
- [CI Pipeline & Docker Specification](../../reference/ci-cd/pipeline.md)
- [CI/CD Strategy & Container Architecture](../../explanation/architecture/ci-cd-and-containers.md)
- [Architecture Overview](../../explanation/architecture/overview.md)
