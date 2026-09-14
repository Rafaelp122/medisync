# [RFC-001] Arquitetura Base e Monólito Modular

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Versão** | 1.0 |
| **Data** | 2026-09-13 |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) |
| **Licença** | MIT / Apache 2.0 (Open Source Permissivo) |
| **Padrão Arquitetural** | Monólito Modular Pragmático com Modelos Ricos (SQLAlchemy 2.0) |
| **Decisão Arquitetural Base** | [ADR-001: Monólito Modular com Modelos Ricos](../adrs/ADR-001-Monolito-Modular-com-Modelos-Ricos.md) |

---

## 1. Contexto & Metas Gerais de Engenharia

O **MediSync Express** é uma plataforma de código aberto voltada para unidades de Pronto-Atendimento Virtual (PA Digital 24/7) sob demanda espontânea. 

Esta RFC estabelece as **fundações estruturais, topologia de serviços, padrões de desenvolvimento e fronteiras modulares** do backend, servindo como o documento base para o ecossistema de especificações técnicas do projeto.

### 1.1 Metas Técnicas Globais (Goals)
- **Modularidade Rigorosa**: Monólito modular estruturado com modelos ricos no SQLAlchemy 2.0, repository e service layer, sem camadas redundantes e com independência estrita entre módulos ([ADR-001](../adrs/ADR-001-Monolito-Modular-com-Modelos-Ricos.md)).
- **Portabilidade & Subida Rápida**: Inicialização declarativa completa do ambiente limpo em menos de 10 minutos via contêineres (`docker compose`), atendendo a instituições com orçamentos e equipes técnicas modestas (RNF-08).
- **Desacoplamento de Infraestrutura**: Componentes como persistência relacional, mensageria/filas, transmissão de vídeo e assinatura digital operam como adaptadores externos desacoplados (RNF-09).
- **Conformidade Regulatória**: Preservação estrita das normas CFM nº 2.314/2022 e LGPD (Art. 11).

### 1.2 Não-Metas Imediatas (Non-Goals)
- **Roteamento de Mídia no Backend**: Processamento ou retransmissão de pacotes RTP/SRTP dentro do runtime Python (delegado inteiramente ao SFU LiveKit via [ADR-007](../adrs/ADR-007-Desacoplamento-de-Midia-LiveKit-SFU.md)).
- **Multi-tenancy Físico Separado**: Criação de banco de dados ou schemas dedicados por cliente nesta fase (adota-se segregação lógica por linha com guarda no ORM via [ADR-003](../adrs/ADR-003-Multi-Tenancy-Logico-no-ORM.md)).
- **Microsserviços Distribuídos**: Decomposição prematura da aplicação em múltiplos serviços de rede independentes.
- **Interoperabilidade RNDS e Padrão TISS na v1.0**: A integração com a Rede Nacional de Dados em Saúde (RNDS) do Ministério da Saúde e a geração de guias de faturamento XML TISS da ANS são não-metas imediatas da versão inicial, ficando planejadas como conectores em versões futuras.

---

## 2. Stack Tecnológica & Rastreabilidade de Decisões

| Camada | Tecnologia | Decisão de Arquitetura (ADR) | Justificativa Técnica |
| :--- | :--- | :--- | :--- |
| **Linguagem & Runtime** | Python 3.12+ | [ADR-001](../adrs/ADR-001-Monolito-Modular-com-Modelos-Ricos.md) | Suporte nativo completo a `asyncio`, type hinting moderno (`TypeIs`, `TypeVarTuple`) e otimizações substanciais de desempenho. |
| **Framework Web** | FastAPI | [ADR-001](../adrs/ADR-001-Monolito-Modular-com-Modelos-Ricos.md) | Alta vazão I/O assíncrona, serialização de contratos OpenAPI/RFC 7807 e injeção de dependências nativa para roteamento fino de serviços. |
| **Persistência Relacional & Migrações** | PostgreSQL 16 + SQLAlchemy 2.0 (Async) + Alembic | [ADR-003](../adrs/ADR-003-Multi-Tenancy-Logico-no-ORM.md), [ADR-004](../adrs/ADR-004-Auditoria-Append-Only-Postgres-Rules.md), [ADR-009](../adrs/ADR-009-Migracoes-Assincronas-Alembic-Asyncpg.md) | Conexões via driver `asyncpg`, listener transparente para injeção de tenant e controle declarativo de migrações assíncronas versionadas. |
| **Fila em Memória & Concorrência** | Valkey 7+ (AOF ativo) | [ADR-002](../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md) | Fork 100% open source do Redis sob licença BSD, provendo estruturas ZSET atômicas e suporte nativo a scripts Lua para transições sem corrida. |
| **Task Worker Assíncrono** | ARQ (`arq` sobre `redis-py` async) | [ADR-005](../adrs/ADR-005-Worker-Assincrono-ARQ-sobre-Valkey.md), [ADR-006](../adrs/ADR-006-Ring-Timeout-Deterministico-via-Jobs-Diferidos.md) | Execução assíncrona nativa em corrotinas, compartilhando pools de banco/HTTP e provendo jobs diferidos determinísticos (`_defer_by`). |
| **Mídia WebRTC** | LiveKit SFU | [ADR-007](../adrs/ADR-007-Desacoplamento-de-Midia-LiveKit-SFU.md) | Cumpre RNF-04 com latência $\le 150\text{ ms}$, operando em processo isolado e desacoplado. |
| **Assinatura Digital & PDF** | PyHanko + ReportLab | [ADR-008](../adrs/ADR-008-Assinatura-Digital-Nuvem-PSC-OAuth2.md) | Emissão de prontuários em PDF/A e assinatura PAdES padrão ICP-Brasil em nuvem via OAuth2/PSC (RNF-06). |
| **Qualidade & Tooling** | `uv`, `ruff`, `basedpyright` (strict), `import-linter`, `pytest-xdist` | [ADR-001](../adrs/ADR-001-Monolito-Modular-com-Modelos-Ricos.md) | Verificação estática rigorosa, execução instantânea de testes e garantia automatizada de limites modulares. |

---

## 3. Estrutura Modular e Diretrizes de Arquitetura

O projeto adota uma divisão em **módulos verticais de negócio**, onde cada módulo encapsula suas regras de domínio e modelos, comunicando-se com o restante do sistema através de interfaces públicas bem definidas.

```plaintext
src/
├── core/                      # Fundações de infraestrutura e serviços transversais
│   ├── config.py              # Configurações tipadas (Pydantic BaseSettings)
│   ├── database.py            # Async engine, sessionmaker e listeners globais
│   ├── valkey.py              # Cliente redis.asyncio e pools de conexões
│   ├── queue.py               # Pool do ARQ e utilitários de enfileiramento
│   ├── context.py             # ContextVar para propagação de contexto (tenant_id)
│   └── security.py            # Hashing Argon2id, tokens JWT e SHA-256
├── migrations/                # Governança de esquema via Alembic Async
│   ├── env.py                 # Runner assíncrono conectado via asyncpg
│   ├── script.py.mako         # Template de migração
│   └── versions/              # Arquivos versionados de migração
├── modules/                   # Módulos verticais independentes (Vertical Slices)
│   ├── identidade/            # models.py, repository.py, service.py, schemas.py, router.py
│   ├── triagem/               # models.py, repository.py, service.py, schemas.py, router.py
│   ├── fila/                  # models.py, repository.py, service.py, schemas.py, router.py, lua/
│   ├── elegibilidade/         # models.py, repository.py, service.py (modo SUS e convênios)
│   ├── teleconsulta/          # models.py, repository.py, service.py, router.py, adapters/ (LiveKit, PSC, S3)
│   ├── auditoria/             # models.py, repository.py, service.py (trilha imutável via triggers)
│   └── telemetria/            # service.py, router.py (OpenMetrics e métricas de plantão)
├── worker.py                  # Entrypoint dos workers assíncronos do ARQ
└── main.py                    # Lifespan, middlewares e inclusão dos routers dos módulos
```

### 3.1 Diretriz Arquitetural: Monólito Modular Pragmático com Modelos Ricos
1. **Modelos Ricos no SQLAlchemy 2.0 (`models.py`)**: As invariantes clínicas, salvaguardas regulatórias (CFM nº 2.314/2022, Portaria SVS/MS nº 344/98) e transições de estado residem diretamente nos métodos das classes do SQLAlchemy 2.0 (`Mapped[...]`). Elimina-se a anemia de negócio e o overhead de "Mapper Hell" (sem entidades puras duplicadas e sem conversores manuais `to_entity`/`to_model`).
2. **Camada de Repositório (`repository.py`)**: Centraliza as queries e operações de persistência do banco relacional, evitando o espalhamento de consultas SQL pela aplicação.
3. **Camada de Serviço (`service.py`)**: Orquestra transações do banco (`session.commit`), invoca os métodos de negócio dos modelos ricos, coordena múltiplos repositórios e integra com gateways externos.
4. **Camada de Apresentação Fina (`router.py`)**: Endpoints FastAPI atuam estritamente como despachantes: validam schemas Pydantic de entrada/saída (`schemas.py`), injetam dependências (`Depends`) e acionam o serviço, sem conter lógica de negócio ou queries de banco.
5. **Defensividade Focada em Volatilidade Externa (`adapters/`)**: Adaptadores isolados são adotados cirurgicamente apenas onde a volatilidade externa real acontece (LiveKit SFU para WebRTC, Provedores PSC para Assinatura ICP-Brasil, Gateways de Mensageria e Object Storage S3/MinIO).

### 3.2 Táticas do Domain-Driven Design (DDD) no Monólito Modular

O DDD é aplicado pragmaticamente para proteger as regras de negócio clínicas sem burocracia de mapeamento:

| Conceito DDD | Implementação no MediSync Express | Responsabilidade |
| :--- | :--- | :--- |
| **Bounded Context** | Módulos Verticais (`src/modules/*`) | Delimita uma área do negócio assistencial com Linguagem Ubíqua própria. |
| **Aggregate Root (Raiz)** | Modelo Rico no SQLAlchemy 2.0 (`models.py`) | Garante integridade e transições de estado através de métodos ricos no próprio objeto. |
| **Invariante de Domínio** | Métodos do Modelo (`atendimento.alocar_para_chamada()`) | Impede estados ilegais (ex: chamar paciente não triado ou emitir receitas proibidas). |
| **Value Object (VO)** | Enums (`StrEnum`), Dataclasses e Tipos Imutáveis | Representa conceitos sem identidade própria (`CPF`, `ScoreFila`, `TipoDocumentoClinico`). |
| **Repository** | Repositório SQLAlchemy (`repository.py`) | Encapsula persistência e consultas, fornecendo interface para obter e salvar o agregado. |
| **Application Service** | Serviço do Módulo (`service.py`) | Orquestra transações (`session.commit`), múltiplos repositórios e eventos. |

### 3.3 Comunicação Inter-Modular em Memória

Em um monólito modular, **a comunicação entre módulos ocorre prioritariamente em memória**, garantindo latência zero ($\approx 0\text{ ms}$), tipagem estrita com `basedpyright` e ausência de overhead de rede/serialização JSON:

1. **Chamada Direta a Serviços Públicos em Memória (Comandos e Consultas Síncronas)**:
   Quando um módulo precisa interagir com outro dentro da mesma transação, ele injeta e invoca o `Service` público do módulo de destino:
   ```python
   # src/modules/fila/service.py
   class FilaService:
       def __init__(self, triagem_service: TriagemService, repo: FilaRepository):
           self.triagem_service = triagem_service
           self.repo = repo

       async def admitir_paciente(self, session: AsyncSession, atendimento_id: int):
           # Invoca a interface pública da triagem em memória (mesma transação ACID)
           dados = await self.triagem_service.obter_dados_acolhimento(session, atendimento_id)
           ...
   ```

2. **Eventos de Domínio em Memória (In-Memory Domain Events)**:
   Para notificações desacopladas do tipo *"algo aconteceu no sistema"* onde o emissor não precisa saber quem vai reagir:
   ```python
   # Disparado ao concluir triagem:
   await event_bus.publish(AtendimentoAptoEvent(atendimento_id=123, prioridade=2))
   # O FilaService reage inserindo no Valkey ZSET sem que a Triagem saiba que a Fila existe!
   ```

### 3.4 Matriz de Decisão: Em Memória vs. Filas Externas (Valkey / ARQ)

O tráfego de dados é estritamente particionado entre o canal em memória e os serviços externos assíncronos:

| Operação | Canal de Execução | Tecnologia | Justificativa de Engenharia |
| :--- | :--- | :--- | :--- |
| **Transições de Estado Clínico** | Em Memória | Python Puro (`Model` / `Service`) | Atomicidade ACID imediata na transação do PostgreSQL. |
| **Consultas Inter-Módulos** | Em Memória | Invocação `await service.metodo()` | Latência $\approx 0\text{ ms}$, tipado em tempo de compilação. |
| **Alocação Concorrente de Chamadas** | Valkey | Script Lua (`alocar_chamada.lua`) | Operação atômica multi-processo entre dezenas de médicos ($\le 5\text{ ms}$). |
| **Ring Timeout de 45 Segundos** | Fora da Memória | Worker ARQ (`_defer_by=45`) | Resolução temporal sem prender threads ou processos dormindo em memória. |
| **Disparo de WhatsApp / SMS** | Fora da Memória | Worker ARQ (Background Job) | I/O externo lento com APIs de terceiros (Meta, Zenvia) que não pode degradar a API REST. |
| **Assinatura Digital ICP-Brasil** | Fora da Memória | Worker ARQ / Adaptador PSC | Chamada HTTP externa com timeout de até 10s e geração de PDF. |

### 3.5 Governança de Fronteiras Modulares (.importlinter)
Para evitar que módulos criem acoplamentos desordenados com modelos ou repositórios internos de outros domínios, as fronteiras são fiscalizadas no CI através do `import-linter`:

```ini
[importlinter]
root_package = src

[importlinter:contract:fronteiras-de-modulos]
name = Isolamento de persistência interna entre módulos
type = forbidden
source_modules =
    src.modules.fila
    src.modules.triagem
    src.modules.teleconsulta
    src.modules.elegibilidade
forbidden_modules =
    src.modules.identidade.models
    src.modules.identidade.repository
    src.modules.triagem.models
    src.modules.triagem.repository

[importlinter:contract:camadas-unidirecionais]
name = Fluxo de dependência interno dos módulos
type = layers
layers =
    src.modules.*.router
    src.modules.*.service
    src.modules.*.repository
    src.modules.*.models
```

---

## 4. Pipeline de Middlewares, Contextos e Tratamento de Erros (RFC 7807)

Toda requisição HTTP recebida pelo FastAPI passa por um pipeline ordenado de middlewares assíncronos que gerenciam segurança, rastreabilidade e injeção de contexto nas `ContextVar` do Python:

```mermaid
flowchart TD
    Req["Requisição HTTP de Entrada"] --> M1["1. CorrelationIdMiddleware<br/>(Gera/Propaga X-Correlation-ID)"]
    M1 --> M2["2. SecurityHeadersMiddleware<br/>(HSTS, CSP, X-Frame-Options DENY)"]
    M2 --> M3["3. AuditContextMiddleware<br/>(Captura IP Real e User-Agent)"]
    M3 --> M4["4. TenantContextMiddleware<br/>(Extrai org_id do JWT e seta ContextVar)"]
    M4 --> Router["Controladores / Endpoints REST"]
    Router -->|Sucesso| Res["Resposta JSON HTTP"]
    Router -->|Exceção Clínica| M5["5. RFC7807ExceptionMiddleware<br/>(application/problem+json)"]
```

### 4.1 Especificação de Erros RFC 7807 (Problem Details)
Erros de negócio e violações de regras clínicas nunca retornam payloads genéricos de erro 500, retornando compulsoriamente a estrutura padronizada da RFC 7807:

```json
{
  "type": "https://medisync.org/errors/paciente-nao-apto",
  "title": "Atendimento Não Apto para Chamada",
  "status": 422,
  "detail": "O atendimento 4521 não concluiu a triagem de Manchester ou a elegibilidade.",
  "instance": "/fila/chamar-proximo",
  "invalid_params": [],
  "correlation_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

### 4.2 Ciclo de Vida da Aplicação (`lifespan` em `main.py`)
No startup da aplicação, antes de receber tráfego:
1. **Pools de Conexão**: Inicializa o `async_engine` do SQLAlchemy, o cliente do Valkey e o pool de enfileiramento do ARQ.
2. **Pré-Carregamento de Scripts Lua**: Carrega o script `alocar_chamada.lua` no Valkey via `SCRIPT LOAD` para otimização com `EVALSHA`.
3. **Auto-Cura da Fila**: Executa `reconciliar_filas_em_memoria` varrendo o PostgreSQL para recompor os ZSETs do Valkey caso o cache tenha reiniciado.
4. **Graceful Teardown**: No encerramento, fecha ordenadamente as conexões pooladas evitando encerramentos abruptos de transações.

---

## 5. Topologia de Implantação e Contêineres (RNF-08)

O ambiente padrão é provisionado via `docker-compose.yml`, permitindo a inicialização completa de todas as dependências em qualquer servidor Linux com Docker instalado:

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    command: sh -c "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:secret@postgres:5432/medisync
      - VALKEY_URL=valkey://valkey:6379/0
      - LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
      - LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - MODO_PUBLICO_SUS=true
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      valkey:
        condition: service_healthy

  worker:
    build:
      context: .
    command: arq src.worker.WorkerSettings
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:secret@postgres:5432/medisync
      - VALKEY_URL=valkey://valkey:6379/0
      - MODO_PUBLICO_SUS=true
    depends_on:
      postgres:
        condition: service_healthy
      valkey:
        condition: service_healthy

  valkey:
    image: valkey/valkey:7.2-alpine
    command: valkey-server --appendonly yes --appendfsync everysec
    volumes:
      - valkeydata:/data
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      retries: 5

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: medisync
      POSTGRES_PASSWORD: secret
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
  valkeydata:
```

---

## 6. Matriz Sequencial de Implementação de RFCs

As RFCs do projeto são ordenadas estritamente pela sua **cadeia de dependência técnica**, ditando a ordem exata em que o sistema deve ser construído sem bloqueios:

1. **[RFC-001: Fundação do Sistema, Arquitetura Base e Tooling](RFC-001-Fundacao-Arquitetura-Base-e-Tooling.md)**: Bootstrap do repositório, topologia Docker, middlewares e linters.
2. **[RFC-002: Modelo de Dados Relacional, Agregados DDD e Migrações](RFC-002-Modelo-de-Dados-Agregados-e-Migracoes.md)**: Diagrama ER, DDL das 8 tabelas centrais, RLS e migração Alembic async.
3. **[RFC-003: Multi-Tenancy, Identidade, Acesso (RBAC) e Auditoria](RFC-003-Multi-Tenancy-Identidade-e-Auditoria.md)**: Autenticação, onboarding progressivo em 2 etapas, RBAC e auditoria append-only imutável.
4. **[RFC-004: Motor de Fila Dinâmica e Concorrência em Memória](RFC-004-Motor-de-Fila-e-Concorrencia-Valkey.md)**: ZSETs no Valkey, script `alocar_chamada.lua` e backpressure estocástico $\alpha$.
5. **[RFC-005: Processamento Assíncrono, Workers ARQ e Resiliência](RFC-005-Processamento-Assincrono-e-Ring-Timeout.md)**: Ring timeout de 45s, sweeper periódico de auto-cura e adaptadores de mensageria (WhatsApp/SMS).
6. **[RFC-006: Teleconsulta WebRTC, Prontuário (PEP) e Assinatura ICP-Brasil](RFC-006-Teleconsulta-WebRTC-e-Assinatura-ICP.md)**: Salas LiveKit SFU, evolução clínica, 5 documentos clínicos e salvaguarda Portaria 344/98.
7. **[RFC-007: Frontend, Painel Clínico e Experiência do Paciente](RFC-007-Frontend-e-Painel-Clinico.md)**: Painel médico unificado, triagem mobile-first e acessibilidade WCAG AA (**Fase 2**).

---

## 7. Governança de Qualidade de Código, Tooling e Engenharia de Testes

Para garantir sustentabilidade de longo prazo, modularidade estrita e prevenção de regressões em produção, o MediSync Express estabelece um pipeline estrito de verificação estática, linters e testes automatizados.

### 8.1 Verificação Estática de Tipos: `basedpyright` (Modo Estrito)
Adota-se o **`basedpyright`** em substituição ao Pyright/Mypy padrão devido à sua análise avançada de exhaustiveness, type narrowing e suporte nativo ao ecossistema moderno do Python 3.12+ (PEP 695).

```toml
# Trecho de pyproject.toml
[tool.basedpyright]
typeCheckingMode = "strict"
pythonVersion = "3.12"
reportMissingTypeStubs = false
reportUnusedImport = true
reportUnusedVariable = true
reportPrivateUsage = "error"
reportConstantRedefinition = "error"
reportIncompatibleMethodOverride = "error"
reportImplicitOverride = "error"
reportUninitializedInstanceVariable = "error"
```

### 8.2 Linter e Formatter de Alta Velocidade: `ruff`
O **`ruff`** unifica formatação e linting em milissegundos, com conjunto estrito de regras ativado para código assíncrono de missão crítica:

```toml
# Trecho de pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E", "W",       # pycodestyle (erros e avisos de sintaxe)
    "F",            # Pyflakes (variáveis não utilizadas, imports quebrados)
    "I",            # isort (ordenação determinística de imports)
    "UP",           # pyupgrade (sintaxe nativa Python 3.12+)
    "B",            # flake8-bugbear (armadilhas de concorrência e argumentos mutáveis)
    "SIM",          # flake8-simplify (simplificação idiomática)
    "TCH",          # flake8-type-checking (move imports de tipagem para TYPE_CHECKING)
    "ASYNC",        # flake8-async (detecção de bloqueio de event loop e timeouts ausentes)
    "S",            # flake8-bandit (auditoria de segurança, SQL injection, secrets)
    "RUF",          # regras nativas avançadas do Ruff
]
ignore = ["S101"]   # Permite assert apenas em arquivos de teste
```

### 8.3 Blindagem da Arquitetura Modular: `import-linter`
Para assegurar matematicamente que a separação de responsabilidades e as fronteiras modulares nunca sejam violadas por novos pull requests, o **`import-linter`** define contratos formais:

```ini
# .importlinter ou pyproject.toml
[importlinter]
root_package = src

[[importlinter.contracts]]
name = "Fluxo Unidirecional de Camadas: Router -> Service -> Repository -> Models"
type = "layers"
layers =
    - src.modules.*.router
    - src.modules.*.service
    - src.modules.*.repository
    - src.modules.*.models

[[importlinter.contracts]]
name = "Proibição de Bypass: Router não acessa Repository diretamente"
type = "forbidden"
source_modules =
    - src.modules.*.router
forbidden_modules =
    - src.modules.*.repository
    - sqlalchemy.orm.Session

[[importlinter.contracts]]
name = "Isolamento Modular Horizontal"
type = "independence"
modules =
    - src.modules.identidade
    - src.modules.triagem
    - src.modules.fila
    - src.modules.teleconsulta
```

### 8.4 Testes Automatizados Paralelizados: `pytest-xdist`
A suíte de testes é estruturada para execução ultrarrápida aproveitando todos os núcleos da CPU via `pytest -n auto`:

```toml
# Trecho de pyproject.toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-n auto --dist loadscope --cov=src --cov-report=term-missing --cov-fail-under=85"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: Testes puros de domínio sem I/O ou banco de dados (execução instantânea)",
    "integration: Testes de integração com banco de dados real e Valkey",
    "e2e: Fluxos completos de atendimento ponta a ponta",
]
```

### 8.5 Geração de Dados de Teste: `polyfactory`
Em vez do `factory_boy` tradicional (acoplado historicamente ao ecossistema síncrono Django), adota-se o **`polyfactory`** (da equipe do Litestar):
- Geração instantânea de entidades baseada em type hints e Pydantic v2.
- Fábricas especializadas (`AtendimentoFactory`, `PacienteFactory`, `DocumentoClinicoFactory`) que geram dados sintéticos válidos (CPFs com dígitos verificadores reais, UUIDs v7, timestamps UTC e históricos de alergias) para testes de regras de negócio sem tocar no banco de dados.
