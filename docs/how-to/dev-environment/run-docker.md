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

### Inspeção interativa e depuração
Caso precise depurar o ambiente de desenvolvimento de forma interativa com shell bash:
```bash
docker run --rm -it -v $(pwd):/app medisync:dev /bin/bash
```

Dentro da sessão interativa, as dependências do ambiente virtual e os comandos da CLI estão disponíveis:
```bash
which python
python -c "import granian; print(granian.__version__)"
exit
```

### Resolução de problemas comuns

1. **Porta em uso (`bind: address already in use`):**
   * Verifique se outra instância local da aplicação ou contêiner está ocupando a porta 8080 ou 8000:
   * `lsof -i :8080` ou `docker ps`
2. **Permissão de arquivos com usuário não-root:**
   * A imagem de produção roda sob UID 1000 (`appuser`). Ao mapear volumes locais para produção, garanta que os arquivos possuam permissão de leitura para o UID 1000.
3. **Erros de importação no boot:**
   * Se um módulo não for encontrado na imagem de produção, confirme se a biblioteca correspondente foi adicionada em `dependencies` no `pyproject.toml` (e não apenas no grupo `dev`).

## Onde no código

- Impl: `Dockerfile:production`
- Spec: `justfile:docker-build`
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
