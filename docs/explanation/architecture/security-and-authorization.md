# Arquitetura de Segurança, Autenticação e Autorização em 3 Camadas

## MediSync Express — Plataforma de Código Aberto para Pronto-Atendimento Virtual (PA Digital 24/7)

| Metadado | Detalhamento |
| :--- | :--- |
| **Frameworks de Referência** | [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) \| [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) |
| **Padrões Criptográficos** | Argon2id (RFC 9106) \| RFC 9562 (UUIDv7) \| JWT / PASETO com chaves assimétricas |
| **Marco Regulatório** | Resolução CFM nº 2.314/2022 \| Resolução CFM nº 1.821/2007 \| Lei Geral de Proteção de Dados (LGPD - Lei nº 13.709/2018) |
| **Status** | Aprovado (Documento Vivo de Arquitetura) |

---

## 1. Princípios Arquiteturais e Separação de Preocupações

Para evitar o acoplamento clássico de sistemas monolíticos onde regras de acesso, hashing de senhas e dados clínicos ficam entrelaçados nas mesmas entidades, o **MediSync Express** adota uma separação estrita de responsabilidades entre três conceitos fundamentais:

```mermaid
flowchart LR
    subgraph Identity ["1. Identidade (Quem você é)"]
        Prof["Profissional<br/>(CRM, UF, Nome, CPF, Papel)"]
        Pac["Paciente<br/>(CNS, Nome Mãe, Alergias)"]
        Org["Organização<br/>(Tenant SUS/Privado)"]
    end

    subgraph AuthN ["2. Autenticação (Como você prova quem é)"]
        Cred["Credenciais & Hashes<br/>(Argon2id, MFA/TOTP)"]
        Sess["Sessão & Tokens<br/>(JWT, Refresh Token, OTP)"]
        Rate["Anti-Brute Force<br/>(Valkey Sliding Window)"]
    end

    subgraph AuthZ ["3. Autorização (O que você pode fazer)"]
        RBAC["Camada 1: Macro RBAC<br/>(Guards de API / FastAPI)"]
        RLS["Camada 2: Tenant RLS<br/>(PostgreSQL 17 Policies)"]
        ABAC["Camada 3: Contexto Clínico<br/>(ABAC: TCLE + Relação Ativa)"]
    end

    Identity -->|Fornece Claims| AuthN
    AuthN -->|Emite Token Validado| AuthZ
```

### Regras Fundamentais de Domínio:
1. **Modelos de Identidade são Puros:** As entidades clínicas em `src/modules/identity/domain/models/` (`Profissional`, `Paciente`, `Organizacao`, `Dependente`) representam cadastros civis e corporativos. **Nenhuma entidade clínica armazena colunas de senha (`senha_hash`) nem executa rotinas criptográficas**.
2. **Autenticação é Desacoplada:** Gerenciamento de credenciais locais, validação de hashes Argon2id, tokens de acesso efêmeros e bloqueios por taxa de requisição residem exclusivamente no módulo de segurança/autenticação (`src/modules/auth/`).
3. **Autorização não é Centralizada na Identidade:** A autorização é distribuída em 3 camadas complementares orientadas ao Princípio do Menor Privilégio (*Least Privilege*) e à Negação por Padrão (*Deny by Default*).

---

## 2. Arquitetura de Autenticação (OWASP AuthN Cheat Sheet)

O sistema opera sob uma **jornada de acesso bimodal**, respeitando a natureza de cada ator:

### 2.1 Atores Corporativos (Profissionais de Saúde e Gestão)
* **Credenciais Fortes:** Senhas corporativas armazenadas exclusivamente sob o algoritmo **Argon2id** (`pwdlib[argon2]`), configurado com parâmetros recomendados pela OWASP e RFC 9106.
* **Mitigação de Força Bruta e Credential Stuffing:** Implementação de contadores de tentativas falhas com janelas deslizantes (*sliding window*) no **Valkey 8.0** em memória. Bloqueio progressivo de IP e conta após 5 tentativas incorretas.
* **Prevenção de Enumeração de Usuários:** Respostas padronizadas sob o formato **RFC 7807 Problem Details** com mensagens genéricas (`"Credenciais inválidas"`), sem revelar se o e-mail ou CPF existe na base.
* **MFA / TOTP:** Suporte mandatório a autenticação multifator para médicos em conformidade com a Resolução CFM nº 2.314/2022 para atos de telemedicina.

### 2.2 Pacientes em Pronto-Atendimento (Passwordless / Efêmero)
* **Zero Fricção na Urgência (Acolhimento < 45s):** Em pronto-atendimento virtual, exigir criação de senhas alfanuméricas complexas antes da triagem causaria risco clínico e abandono.
* **Tokens Efêmeros de Ingestão:** Durante as Fases 1 e 2 do cadastro progressivo, o paciente recebe um token temporário assinado e autenticação baseada em posse via código OTP (One-Time Password) de 6 dígitos enviado por SMS/WhatsApp.
* **Acesso Pós-Consulta:** Documentos assinados digitalmente (receitas e atestados) são entregues via links assinados com tempo de expiração curto e validados pelo código de autenticidade do documento ICP-Brasil.

---

## 3. Modelo de Autorização em 3 Camadas (OWASP AuthZ Cheat Sheet)

A decisão de autorização segue uma estratégia em profundidade (*Defense in Depth*):

```mermaid
sequenceDiagram
    autonumber
    actor Med as Médico Plantonista
    participant API as Camada 1: API Gateway (RBAC)
    participant DB as Camada 2: PostgreSQL (Tenant RLS)
    participant Mod as Camada 3: Módulo Consulta (ABAC)

    Med->>API: GET /api/v1/consultations/{id}/prontuario (Bearer JWT)
    Note over API: Valida assinatura do token e papel MEDICO
    alt Papel inválido
        API-->>Med: 403 Forbidden (RBAC)
    end

    API->>DB: Inicia transação e define app.current_tenant_id = 42
    Note over DB: Políticas de RLS filtram automaticamente pelo tenant

    API->>Mod: Solicita abertura de prontuário
    Note over Mod: Valida TCLE assinado + se Médico é o responsável ativo
    alt Sem relação ativa ou sem TCLE
        Mod-->>Med: 403 Forbidden (Violação Deontológica CFM)
    end

    Mod-->>Med: 200 OK (Dados do Prontuário Liberados)
```

### Camada 1: Macro-Autorização na Borda da API (RBAC)
* **Objetivo:** Filtrar o acesso a endpoints baseado nas atribuições funcionais (*roles*).
* **Implementação:** Injeção de dependências nativa do FastAPI (`Depends(require_role("MEDICO"))` ou `Depends(require_permission("atendimentos:chamar"))`).
* **Regra OWASP:** *Deny by Default*. Rotas protegidas rejeitam requisições sem claims explícitas válidas.

### Camada 2: Isolamento de Dados Multitenant (PostgreSQL Row-Level Security - RLS)
* **Objetivo:** Impedir o vazamento de dados entre prefeituras e operadoras distintas (*cross-tenant leakage*), eliminando a vulnerabilidade de *IDOR (Insecure Direct Object Reference)*.
* **Implementação:** O `TenantResolutionMiddleware` intercepta a requisição, valida o tenant ativo e injeta a variável de sessão `set_config('app.current_tenant_id', :tenant_id, true)`.
* **Políticas no Banco:** As tabelas mestres e transacionais possuem `FORCE ROW LEVEL SECURITY`:
  ```sql
  CREATE POLICY tenant_isolation_pacientes ON pacientes
      USING (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::BIGINT);
  ```

### Camada 3: Micro-Autorização de Contexto Clínico (ABAC / ReBAC)
* **Objetivo:** Garantir a conformidade legal e deontológica do sigilo médico (CFM nº 1.821/2007 e LGPD).
* **Por que não fica na Identidade:** A regra depende do estado transacional da fila e do atendimento, que residem nos módulos `queue` e `consultation`.
* **Regras de Avaliação:**
  1. O paciente concedeu aceite explícito ao TCLE digital (`tcle_hash IS NOT NULL`)?
  2. O ciclo de vida do atendimento permite a operação solicitada:
     - **Leitura do Prontuário (`is_mutation=False`):** `EM_ATENDIMENTO`, `CHAMANDO_PACIENTE` ou `CONCLUIDO` (Resolução CFM nº 1.821/2007 — Guarda de Prontuário e Acesso Histórico pelo Médico Assistente).
     - **Mutações Clínicas (`is_mutation=True`):** estritamente `EM_ATENDIMENTO` ou `CHAMANDO_PACIENTE` (Resolução CFM nº 2.314/2022). Tentativas de mutação em atendimento `CONCLUIDO` são bloqueadas com erro 403 Forbidden.
  3. O médico autenticado é exatamente o `medico_id` atribuído ao atendimento?
  *Se qualquer condição for falsa, o acesso aos dados sensíveis do prontuário é bloqueado com erro 403.*

---

## 4. Segurança em Comunicação em Tempo Real, WebSockets e LiveKit

O MediSync Express utiliza WebSockets e WebRTC para sinalização e streaming contínuo (posição da fila, notificações ao médico de plantão e teleconsulta via LiveKit SFU). Por manterem conexões assíncronas persistentes, esses canais exigem salvaguardas específicas contra ataques de exaustão e violação de sigilo:

```mermaid
sequenceDiagram
    autonumber
    actor Cliente as Cliente (Médico / Paciente)
    participant FastAPI as FastAPI DI Engine
    participant Guard as Guard WsAuthDep
    participant DB as PostgreSQL (Sessão Efêmera)
    participant Endpoint as Router WS / Valkey PubSub

    Cliente->>FastAPI: Handshake WS: /ws/.../?token=<credencial>
    Note over FastAPI: FastAPI intercepta antes de websocket.accept()
    FastAPI->>Guard: Executa Guard de Segurança
    Guard->>Guard: Valida formato, expiração e revogação no Valkey (4401)
    Guard->>DB: Abre sessão efêmera pontual para checar ReBAC/Posse
    DB-->>Guard: Confirma posse / alocação
    Note over DB: Sessão fechada imediatamente (Zero Starvation)
    alt Falha de Autenticação ou Autorização
        Guard-->>FastAPI: Levanta WebSocketException(code=4401 ou 4403)
        FastAPI-->>Cliente: Fecha conexão imediatamente (sem accept)
        Note over Endpoint: Endpoint NUNCA é executado!
    else Sucesso
        Guard-->>FastAPI: Retorna None
        FastAPI->>Endpoint: Executa endpoint WS
        Endpoint->>Cliente: websocket.accept() e streaming via Valkey
    end
```

### 4.1 Handshake Seguro e Encerramento Prematuro (RFC 6455)
* **Credenciais na Query String:** Como clientes WebSocket nativos em navegadores web não permitem injetar cabeçalhos HTTP customizados (`Authorization: Bearer`), a credencial é transmitida no parâmetro de URL `?token=<jwt|hmac>`.
* **Códigos de Fechamento Customizados:** Em conformidade com as faixas de aplicação da RFC 6455, conexões não autorizadas são encerradas com:
  - **`4401` (Unauthorized):** Token ausente, expirado, inválido ou revogado no Valkey.
  - **`4403` (Forbidden):** Papel incorreto, médico não alocado ou paciente sem titularidade sobre o atendimento.
* **Rejeição Pré-Accept:** O fechamento ocorre **antes** de chamar `websocket.accept()`. Isso economiza alocação de buffers no servidor e impede que clientes não autenticados consumam recursos do runtime.

### 4.2 Guards de Efeito Colateral no FastAPI (`_auth: *WsAuthDep`)
* **Por que declarar na assinatura:** No framework FastAPI/Starlette, o decorator `@router.websocket(...)` **não possui** o parâmetro `dependencies=[...]` existente em rotas HTTP normais.
* **Mecanismo de Execução Automática:** A dependência é tipada como `Annotated[None, Depends(validar_ws_*_token)]` e declarada com prefixo sublinhado (`_auth: QueueWsAuthDep` ou `_auth: DoctorWsAuthDep`).
* **Garantia de Execução:** O motor de injeção de dependências do FastAPI inspeciona a assinatura e **obrigatoriamente executa a dependência antes** de invocar o corpo do endpoint. Se a validação lançar `WebSocketException`, o endpoint nunca é chamado. O prefixo `_` apenas sinaliza ao linter que o valor de retorno (`None`) não precisa ser lido dentro do router.

### 4.3 Prevenção de Esgotamento do Pool de Banco de Dados (Anti-Starvation)
* **O Risco:** Endpoints de WebSocket mantêm streams abertos por longos períodos (minutos a horas). Injetar `session: DbSessionDep` diretamente no router prenderia uma conexão do pool do PostgreSQL por toda a duração da conexão do cliente, esgotando rapidamente o pool da aplicação.
* **A Solução:** As verificações de posse e autorização utilizam sessões efêmeras pontuais (ex.: `default_verificar_posse_paciente_fila` via `async_session_factory`), abrindo e liberando a conexão com o banco de dados em milissegundos durante o handshake. O streaming contínuo subseqüente consome exclusivamente recursos do Valkey Pub/Sub.

### 4.4 Blindagem na Emissão de Tokens LiveKit SFU (WebRTC)
No endpoint `POST /consultations/{atendimento_id}/livekit/token`:
* **Anti-Enumeração:** A validação de token (401 RFC 7807) é executada **antes** de qualquer consulta ao banco de dados, impedindo que atacantes sem credenciais válidas descubram IDs de atendimentos ou pacientes.
* **Micro-Autorização ReBAC:** O token LiveKit só é emitido se o médico autenticado for o médico alocado no atendimento ativo (ou paciente titular), se o `participant_id` coincidir com a identidade do chamador e se o atendimento não estiver em status terminal.
* **Isolamento Multitenant:** Validação estrita da correspondência entre a `organizacao_id` (inteiro) do token, da URL e do atendimento.

---

## 5. Matriz de Acesso e Papéis Corporativos (RBAC)

| Recurso / Ação | ADMIN_GLOBAL | GESTOR_UNIDADE | MEDICO | FATURAMENTO | PACIENTE (Token) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Configurar TMA / Parâmetros da Unidade** | Sim | Sim | Não | Não | Não |
| **Cadastrar / Desativar Profissionais** | Sim | Sim (sua org) | Não | Não | Não |
| **Visualizar Fila Geral da Unidade** | Sim | Sim | Sim | Não | Não |
| **Chamar Próximo Paciente da Fila** | Não | Não | Sim | Não | Não |
| **Visualizar / Editar Prontuário Ativo** | Não | Não | Sim (se alocado) | Não | Não |
| **Assinar Receitas e Atestados (ICP)** | Não | Não | Sim (se alocado) | Não | Não |
| **Consolidar Lotes de Faturamento** | Sim | Sim | Não | Sim | Não |
| **Acompanhar Posição na Fila / TME (WS)** | Não | Não | Não | Não | Sim (seu id) |
| **Notificações de Chamada Médica (WS)** | Não | Não | Sim (seu id) | Não | Não |
| **Visualizar Documentos Próprios** | Não | Não | Não | Não | Sim (seu id) |

---

## 6. Rastreabilidade de Implementação

A arquitetura descrita é implementada e auditada através das seguintes issues do repositório:

* **[Issue #11](https://github.com/Rafaelp122/medisync/issues/11)**: `feat(security): implement PostgreSQL Row-Level Security (RLS) policies` (Camada 2 - Tenant Isolation).
* **[Issue #35](https://github.com/Rafaelp122/medisync/issues/35)**: `feat(auth): implement OWASP authentication service, Argon2id verification, rate limiting and JWT session management` (Autenticação Desacoplada).
* **[Issue #36](https://github.com/Rafaelp122/medisync/issues/36)**: `feat(authz): implement OWASP multi-tier authorization guards (RBAC, API policies and clinical ABAC/ReBAC context)` (Camadas 1 e 3 - RBAC e ABAC Clínico).
* **[Issue #39](https://github.com/Rafaelp122/medisync/issues/39)**: `fix(security): blindar mutações clínicas do PEP e leitura na ClinicalAccessPolicy` (Blindagem de Mutações e Acesso Histórico ao PEP).
* **[Issue #12](https://github.com/Rafaelp122/medisync/issues/12)**: `feat(identity): implement progressive 2-phase onboarding API and dependent management` (Cadastro Progressivo do Paciente).
* **[Issue #40](https://github.com/Rafaelp122/medisync/issues/40)**: `fix(identity): implementar prova de posse via intake token no onboarding Fase 2 e dependentes` (Blindagem contra IDOR no Onboarding e Dependentes).
* **[Issue #42](https://github.com/Rafaelp122/medisync/issues/42)**: `feat(security): blindar emissão de tokens LiveKit e autenticar WebSockets com códigos 4401/4403 e guards ReBAC` (Segurança em WebSockets e LiveKit SFU).
