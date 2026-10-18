# Onboarding quickstart

> Guia prático passo a passo: do ambiente virgem até a API respondendo localmente com qualidade e segurança validadas em ~15min.

## Visão geral

Bem-vindo ao MediSync Express! Este tutorial orienta desenvolvedores novatos na preparação completa do ambiente local. Ao final deste roteiro, você terá a infraestrutura de contêineres ativa, dependências instaladas, banco de dados migrado, portão de qualidade aprovado, servidor Granian respondendo requisições e verificações de segurança ativas.

### Pré-requisitos obrigatórios

Antes de iniciar, certifique-se de ter instalado em sua estação de trabalho:
- **Python 3.12+**: Interpretador padrão do ecossistema.
- **uv**: Gerenciador ultrarrápido de pacotes e ambientes virtuais.
- **just**: Executor de comandos canônicos definidos no `justfile`.
- **Docker e Docker Compose v2**: Orquestrador da topologia de serviços locais.

---

## Passo 1: Inicialização e inspeção da infraestrutura local

O MediSync Express utiliza contêineres Docker para seus serviços auxiliares:
- **PostgreSQL 17**: Banco relacional primário para dados cadastrais e clínicos.
- **Valkey 8**: Armazenamento em memória para cache de alta performance e filas assíncronas ARQ.
- **LiveKit SFU**: Servidor WebRTC para teleconsultas em tempo real.
- **MinIO S3**: Armazenamento de objetos compatível com AWS S3 para laudos e gravações.

Suba toda a topologia em segundo plano e aguarde a prontidão dos serviços:

```bash
just up
```

Em seguida, inspecione o estado dos contêineres para confirmar a prontidão:

```bash
just ps
```

Todos os serviços principais devem apresentar status `healthy` ou `running`.

---

## Passo 2: Sincronização de dependências e configuração de ambiente

Com a infraestrutura ativa, sincronize as dependências travadas do projeto com o comando canônico do `justfile`:

```bash
just install
```

O comando aciona `uv sync` internamente, criando o virtualenv isolado em `.venv/` com as versões de `pyproject.toml`.

Copie o contrato de variáveis de ambiente pré-configuradas:

```bash
cp .env.example .env
```

O arquivo `.env.example` fornece credenciais e portas locais compatíveis com os serviços do `docker-compose.yml`.

---

## Passo 3: Migração do banco relacional e histórico

Com o PostgreSQL saudável, aplique o esquema relacional:

```bash
just migrate
```

O comando executa `alembic upgrade head`, aplicando as migrações em ordem estrita.

Para visualizar o histórico cronológico e conferir se a versão atual está no topo:

```bash
just migration-history
```

A saída exibirá a árvore linear de revisões com o identificador atual marcado como `(head)`.

---

## Passo 4: Execução do portão de qualidade completo

Antes de rodar a aplicação, verifique a conformidade de todo o repositório:

```bash
just check
```

O `just check` executa sequencialmente com fail-fast estrito:
1. **fmt**: Validação e formatação de código com Ruff.
2. **lint**: Análise estática com correções seguras via Ruff.
3. **typecheck**: Checagem de tipos estáticos com Basedpyright em modo estrito.
4. **tach**: Auditoria de fronteiras modulares e arquitetura hexagonal via Tach.
5. **unit**: Bateria de testes unitários rápidos e testes de arquitetura.
6. **integration**: Testes de integração end-to-end com Postgres, Valkey, LiveKit e MinIO reais.

Todas as etapas devem terminar verdes com código de saída 0.

---

## Passo 5: Inicialização do servidor Granian e primeiro request

Inicie o servidor HTTP Granian em modo ASGI com hot-reload ativo:

```bash
uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000 --reload
```

Em outro terminal, dispare o primeiro teste de verificação de saúde da API:

```bash
curl -s http://localhost:8000/healthz | jq .
```

A resposta retornará um payload JSON contendo `status: ok` e a versão do sistema.

Acesse a documentação interativa gerada automaticamente no navegador:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Passo 6: Configuração de segurança local e auditoria de segredos

Para proteger o repositório contra commits acidentais de credenciais ou chaves, instale os hooks de pre-commit e execute a auditoria de segredos:

```bash
just pre-commit-install
just scan-secrets
```

O Gitleaks (ADR-010) analisará os arquivos monitorados e histórico em busca de chaves ou senhas expostas.

---

## Passo 7: Encerramento do ambiente

Ao encerrar sua sessão de desenvolvimento, pare os contêineres locais:

```bash
just down
```

Os dados persistentes em volumes serão preservados para a sua próxima sessão de trabalho.

---

## Próximos passos

Com o ambiente devidamente inicializado e validado:
- Siga para o tutorial [Backend first feature](backend-first-feature.md) para implementar seu primeiro endpoint fino.
- Consulte o guia prático [Setup local detalhado](../how-to/dev-environment/setup-local.md) para operações avançadas.
- Consulte [Executar testes](../how-to/backend/run-tests.md) para aprofundar na estratégia de testes.
