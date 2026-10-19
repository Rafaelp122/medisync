# MediSync Express — Plataforma de Pronto-Atendimento Virtual (PA Digital 24/7)

> **Infraestrutura aberta de pronto-atendimento virtual sob demanda espontânea com motor de fila atômica, teleconsulta WebRTC desacoplada, salvaguarda de deterioração clínica e governança regulatória brasileira.**

---

## 📌 Contexto do Projeto & Isenção de Escopo (Portfolio Disclaimer)

> [!IMPORTANT]
> **Natureza do Projeto:**
> O **MediSync Express** é um **projeto conceitual de engenharia de software e arquitetura avançada desenvolvido para fins de portfólio técnico**.
>
> **O que este projeto É:**
> * Um estudo de caso aprofundado de engenharia de software moderna, modelagem orientada a domínio (DDD) e padrões de alta concorrência;
> * Um sistema projetado estritamente sobre **marcos regulatórios reais e oficiais da saúde brasileira** (Resoluções CFM nº 2.314/2022 e 1.821/2007, Art. 11 da LGPD, Portaria SVS/MS nº 344/98 e RDC ANVISA nº 20/2011);
> * Uma demonstração prática de padrões arquiteturais sênior em Python: **Hexagonal Pragmático**, contratos via `typing.Protocol` (PEP 544), controle de concorrência atômica com scripts Lua no Valkey, Row-Level Security (RLS) no PostgreSQL, workers assíncronos em corrotinas nativas com ARQ e auditoria estrita de fronteiras modulares com **Tach**.
>
> **O que este projeto NÃO É:**
> * Não é fruto de pesquisa de campo empírica com usuários finais (*user research*), entrevistas com médicos/pacientes reais, validação de mercado em estágio inicial (*market discovery*), testes clínicos com humanos ou um MVP de startup em operação comercial;
> * Não constitui um dispositivo médico homologado pela ANVISA nem deve ser utilizado em ambiente de assistência real a pacientes sem prévia validação clínica, comitê de ética e auditoria de segurança institucional.

---

## 🎯 Visão Geral da Solução

O **MediSync Express** foi concebido para endereçar um dos maiores gargalos dos sistemas de saúde públicos e privados: a sobrecarga de prontos-socorros físicos por queixas de baixa e média complexidade (fichas verdes e azuis).

A plataforma opera sob regime de **demanda espontânea (sem agendamento prévio)** através de uma esteira assistencial contínua:

```mermaid
flowchart LR
    A["1. Acolhimento Ágil<br/>(TCLE Hash < 45s)"] --> B["2. Fila Dinâmica<br/>(Valkey ZSET + SAMU 192)"]
    B --> C["3. Validação Concorrente<br/>(Faturamento / SUS No-Op)"]
    C --> D["4. Teleconsulta Integrada<br/>(LiveKit SFU + PEP)"]
    D --> E["5. Emissão & Auditoria<br/>(PAdES ICP-Brasil + S3)"]
```

### 🏛️ Dualidade Operacional Nativa (SUS vs. Saúde Privada)
* **Atenção Pública (SUS)**: Entrada universal via CPF ou Cartão Nacional de Saúde (CNS). A validação de cobertura opera como instrução nula (*no-op*), inserindo o cidadão imediatamente na esteira de atendimento médico com custo de infraestrutura reduzido para municípios.
* **Saúde Suplementar / Particular**: Pacientes ingressam na fila sem paywalls obstrutivos na tela inicial. A validação de elegibilidade de convênio ocorre de forma concorrente em segundo plano enquanto o paciente aguarda; em caso de pendência ou rejeição temporária, o paciente é alertado e pode optar por contingência assistencial imediata ou reenvio de dados (`POST /api/v1/fila/atendimentos/{id}/regularizar`), preservando rigorosamente seu tempo de espera original na fila virtual ($T_0$ / NC-QUE-04).

---

## ⚡ Destaques de Arquitetura e Engenharia

A arquitetura do MediSync Express foi desenhada para resolver tensões reais de concorrência, desempenho e segurança da informação:

```mermaid
flowchart TD
    subgraph Clients["Camada de Cliente"]
        Web["Web SPA / PWA Mobile-First<br/>(WCAG 2.1 AA / WebRTC)"]
    end

    subgraph CoreBackend["Backend Modular (FastAPI + Python 3.12+)"]
        Auth["modules/auth<br/>(Argon2id, OTP & RBAC)"]
        Triage["modules/triage<br/>(Acolhimento & TCLE)"]
        Queue["modules/queue<br/>(Fila Dinâmica & Lua)"]
        Identity["modules/identity<br/>(Multi-Tenancy & Organizações)"]
        Consultation["modules/consultation<br/>(PEP & LiveKit Tokens)"]
        Billing["modules/billing<br/>(Elegibilidade & SUS)"]
        Telemetry["modules/telemetry<br/>(Painel CQRS & Métricas)"]

        Protocols["typing.Protocol (PEP 544)<br/>(Portas de Entrada e Notificadores Ponto a Ponto)"]
    end

    subgraph Infra["Infraestrutura Dedicada"]
        Postgres[(PostgreSQL 17<br/>Modelos Ricos + RLS Nativo)]
        Valkey[(Valkey 8.0<br/>ZSET + Script Lua + Pub/Sub)]
        LiveKitSFU["LiveKit SFU (Go)<br/>(Streaming WebRTC SRTP)"]
        ARQWorker["ARQ Task Worker<br/>(Jobs Diferidos Ring Timeout)"]
        S3Storage[(MinIO / S3<br/>PDFs de Prescrições PAdES)]
    end

    Web -->|HTTPS / WSS| CoreBackend
    Web -->|SRTP Media| LiveKitSFU

    CoreBackend --> Postgres
    CoreBackend --> Valkey
    CoreBackend --> LiveKitSFU
    CoreBackend --> S3Storage

    ARQWorker --> Valkey
    ARQWorker --> Postgres
```

### 1. Hexagonal Pragmático (Zero "Mapper Hell")
* **Modelos Ricos no SQLAlchemy 2.0**: As entidades persistidas (`Mapped[...]`) não são meras bolsas de dados anêmicas; elas encapsulam as regras clínicas, validações e máquinas de estado (ex.: `atendimento.alocar_para_medico()`).
* **Eliminação de Mappers Duplicados**: Não há classes DTO duplicadas puras para persistência relacional, eliminando o tributo de manutenção de conversores manuais (`to_domain`/`to_orm`).
* **Subtipagem Estrutural com `typing.Protocol` (PEP 544)**: Portas de saída para componentes voláteis (Valkey, LiveKit, certificadoras ICP-Brasil e MinIO/S3) operam via *static duck typing*, sem herança rígida de `abc.ABC`.

### 2. Comunicação Inter-Módulos em Duas Vias
* **Síncrona (Comandos / Consultas)**: Módulos expõem contratos via `typing.Protocol`. Nenhum módulo importa modelos internos ou repositórios de outro context.
* **Assíncrona (Notificações Ponto a Ponto)**: Notificadores desacoplados via ports (`PacienteAusenteNotifierPort`, `QueueOverflowNotifierPort`, `ElegibilidadeNotifierPort`) com DTOs imutáveis, sem barramento central ou acoplamento relacional.

### 3. Concorrência Atômica de Fila em $\le 200\text{ ms}$ (Valkey 8.0 & Lua)
* Fila indexada em **Sorted Sets (ZSET)** com pontuação determinística de 64 bits e identificadores em **UUIDv7**:
  $$\text{Score} = (\text{prioridade\_clinica} \times 10^{12}) + \text{timestamp\_entrada\_epoch}$$
* **Desempate Determinístico FIFO via UUIDv7 (RN01)**: Membros com o mesmo score são desempatados nativamente por ordem lexicográfica no Valkey. Como o UUIDv7 embute timestamp de milissegundos em seus primeiros dígitos, a cronologia de entrada é preservada com precisão absoluta.
* Alocação médico-paciente executada em uma única operação indivisível via script Lua (`alocar_chamada.lua`), aplicando travas duplas vinculadas de 45 segundos (`lock:medico` e `lock:atendimento`) com códigos discriminados (`0` para médico ocupado e `-1` para retry de atendimento).

### 4. Resolução Determinística de No-Show (Ring Timeout de 45s no ARQ)
* Eliminação de deadlocks operacionais quando o paciente não atende a chamada médica.
* Agendamento de precisão via tarefas diferidas no ARQ (`_defer_by=timedelta(seconds=45)`), superando a fragilidade e imprecisão de eventos pub/sub de expiração de chaves (`notify-keyspace-events`) do Redis.

### 5. Multi-Tenancy com Defesa em Profundidade no PostgreSQL (RLS)
* Segregação lógica de dados entre municípios e operadoras orientada por `organizacao_id`.
* O tenant ativo é isolado via `ContextVar` assíncrona por requisição e forçado nativamente no motor do PostgreSQL 17 via **Row-Level Security (RLS)** (`SET LOCAL app.current_tenant_id`), impedindo vazamento de dados mesmo em caso de falha de filtro no código de aplicação.

### 6. Isolamento e Governança Modular com Tach
* Controle contínuo de dependências auditado pelo **[Tach](https://github.com/gauge-sh/tach)** (escrito em Rust).
* O comando `tach check` é executado no pipeline de integração contínua (CI), barrando em tempo de compilação qualquer acoplamento indevido ou importação de arquivos privados entre os módulos.

---

## 📂 Estrutura Modular do Código (`src/`)

```plaintext
src/
├── core/                              # Fundações transversais da aplicação
│   ├── audit/                         # Trilha de auditoria imutável append-only
│   ├── config.py                      # Configurações tipadas (Pydantic BaseSettings)
│   ├── database.py                    # Engine assíncrona SQLAlchemy e sessionmaker
│   ├── valkey.py                      # Pool de conexões assíncronas do Valkey
│   └── telemetry.py                   # Instrumentação Prometheus e métricas operacionais
│
└── modules/
    ├── auth/                          # Autenticação Argon2id, lockout, OTP passwordless e revogação
    ├── billing/                       # Elegibilidade assíncrona e modo SUS no-op
    ├── consultation/                  # PEP SOAP, LiveKit WebRTC e assinatura digital ICP-Brasil
    ├── identity/                      # Cadastro bifásico, dependentes e isolamento de tenant
    ├── queue/                         # Fila dinâmica ZSET 64-bit, scripts Lua e ring timeout 45s
    ├── telemetry/                     # Painel analítico CQRS, cache volátil 5s e governança estocástica
    └── triage/                        # Acolhimento ágil, TCLE hash e rota SAMU 192
```

---

## 📚 Documentação Técnica Completa

A governança do repositório é estritamente segregada em três pilares ortogonais fundamentados no referencial metodológico de Engenharia de Requisitos (Vazquez & Simões) e complementada por blueprints técnicos e ADRs:

| Documento | Pilar Metodológico | Conteúdo Central |
| :--- | :--- | :--- |
| **[Business Vision](docs/explanation/business-vision.md)** | *Problem Space* (O Porquê) | Contexto de PA Virtual 24/7, Canvas de Requisitos, Metas SMART, Personas e Matriz de Necessidades de Negócio (NEC-01 a NEC-08). |
| **[Product Specification](docs/explanation/product-specification.md)** | *Solution Space* (O Quê) | Invariantes Formais de Domínio (**RN01 a RN07**), Requisitos Funcionais (**RF-01 a RF-10**) e Matriz de Rastreabilidade Vertical. |
| **[User Stories & Living Specs](docs/user-stories/README.md)** | *Living Specifications* (Qualidade & BDD) | Linha de base comportamental em Gherkin puro, checklists técnicos de inspeção e rastreabilidade vertical ([US-01 a US-13](docs/user-stories/README.md)). |
| **[Architecture Overview](docs/explanation/architecture/overview.md)** | *Engineering Foundations* (O Como) | Hexagonal Pragmático, protocolos, Event Bus, diagramas C4 (Contexto e Contêineres) e Matriz FURPS+ / ISO 25010. |
| **[Data Model](docs/explanation/architecture/data-model.md)** | Blueprint Técnico | Diagrama Entidade-Relacionamento (DER), DDL das 10 tabelas relacionais, regras de RLS e snapshots forenses do CFM. |
| **[Concurrency & Queues](docs/explanation/architecture/concurrency-and-queues.md)** | Blueprint Técnico | Script Lua atômico (`alocar_chamada.lua`), fórmula do score do ZSET e resolução determinística de No-Show via ARQ. |
| **[Compliance & Telemedicine](docs/explanation/architecture/compliance-and-telemedicine.md)** | Blueprint Técnico | Topologia LiveKit SFU WebRTC, fluxo de assinatura digital PAdES-LTV com PyHanko e guarda em Object Storage S3/MinIO. |
| **[Architecture Decision Records (ADRs)](docs/adrs/README.md)** | Governança & Trade-offs | Registro formal das 10 decisões estruturais fundamentais ([ADR-001 a ADR-010](docs/adrs/README.md)). |

---

## 🛠️ Stack Tecnológica

| Camada | Tecnologia Adotada | Papel Arquitetural |
| :--- | :--- | :--- |
| **Linguagem & Runtime** | Python 3.12+ | Tipagem moderna (`typing.Protocol`, `TypeIs`), alta performance assíncrona. |
| **Framework Web API** | FastAPI + Granian (Rust) | Runtime ASGI em Rust de altíssima vazão, WebSockets nativos, latência ultra-baixa e OpenAPI. |
| **Persistência Relacional** | PostgreSQL 17 + SQLAlchemy 2.0 Async | Modelos de domínio ricos (`Mapped[...]`), queries assíncronas nativas com `psycopg 3` (`psycopg[binary]`). |
| **Isolamento de Dados** | PostgreSQL Row-Level Security (RLS) | Blindagem multi-tenant no nível do kernel do banco de dados. |
| **Fila em Memória & Locks** | Valkey 8.0 (AOF ativo) | ZSET atômico com scripts Lua para alocação médico-paciente sem condições de corrida. |
| **Task Worker Assíncrono** | ARQ (`arq` sobre `asyncio`) | Tarefas em background e resolução de Ring Timeout de 45 segundos via jobs diferidos. |
| **Mídia em Tempo Real** | LiveKit SFU (Go) | Roteamento de áudio/vídeo WebRTC seguro (SRTP) com latência $\le 150\text{ ms}$. |
| **Assinatura Digital & PDF** | PyHanko + ReportLab | Emissão de receitas e atestados em PDF/A com assinatura PAdES-LTV padrão ICP-Brasil. |
| **Object Storage** | MinIO / AWS S3 | Guarda perene de documentos clínicos assinados com entrega via Presigned URLs. |
| **Qualidade & Fronteiras** | Tach, Ruff, basedpyright (strict), pytest | Verificação estática de tipos, formatação ultrarrápida e auditoria de limites modulares. |

---

### 🛡️ Governança de Routers Finos e Envelope RFC 7807 (ADR-001 / ADR-008)

A camada de apresentação do MediSync Express opera sob o padrão estrito de **Routers Finos**, auditado no CI por testes de AST:
* **Zero Lógica de Negócio em Routers**: Routers nunca importam SQLAlchemy, repositórios ou modelos internos; serviços são injetados exclusivamente via dependências tipadas (`*Dep`) resolvidas no composition root (`composition.py`).
* **Prefixo Único e Segregação**: Toda a API HTTP pública e autenticada reside sob o prefixo `/api/v1`. WebSockets operam sob rotas dedicadas `/ws`.
* **Envelope Canônico de Erros RFC 7807**: Falhas clínicas e operacionais (`NotFoundError`, `ConflictError`, `ValidationError`) são traduzidas deterministicamente pelo middleware de exceções no padrão RFC 7807 Problem Details (detalhado em [Error Envelope](docs/reference/api/error-envelope.md)).
* **Proteção por Rate Limit**: Endpoints sensíveis (validação pública de documentos e download de prescrições) possuem controle de vazão atômico por IP no Valkey com headers padronizados de `Retry-After`.

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
* Python 3.12 ou superior instalado;
* Gerenciador de pacotes [`uv`](https://github.com/astral-sh/uv);
* Docker e Docker Compose instalados na máquina.

### 1. Inicialização Completa do Ambiente (Setup Dev)
Clone o repositório e execute a receita consolidada para provisionar o ambiente local em um único comando:
```bash
git clone https://github.com/Rafaelp122/medisync.git
cd medisync
just setup-dev
```
*O comando `just setup-dev` cria o arquivo `.env` a partir de `.env.example`, sobe os contêineres Docker saudáveis, sincroniza dependências com `uv`, aplica migrações do banco com Alembic e executa o portão rápido em memória.*

### 2. Validação Rápida em Memória (Zero Docker, ~15 segundos)
Para avaliadores técnicos que desejam validar o código imediatamente sem iniciar serviços Docker:
```bash
just check-fast
```
*Executa estaticamente: varredura de segredos (Gitleaks), linter de docs, auditoria de clean code para IA, formatação (Ruff), tipagem estrita (basedpyright), fronteiras modulares (Tach) e suíte unitária/arquitetural paralela.*

### 3. Execução dos Serviços Locais
```bash
# Iniciar o servidor HTTP ASGI de alta performance (Granian)
uv run granian --interface asgi --reload src.main:app

# Em outro terminal: iniciar o background worker ARQ para ring timeout de 45s
just worker
```

### 4. Portão de Qualidade Completo (com Infraestrutura Real)
```bash
just check
```

---

## ⚖️ Licença

Este projeto é distribuído sob os termos da licença permissiva **MIT / Apache 2.0**. Consulte o arquivo `LICENSE` para mais informações.
