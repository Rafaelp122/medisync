# [ADR-013] Simplificação para Plataforma Única e Remoção de Multi-Tenancy & RLS

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-11-20 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Substitui** | [ADR-003](ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md) (Superseded); revisa parcialmente [ADR-012](ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md) (§4.2) |
| **Referência** | [Overview](../explanation/architecture/overview.md), [Data Model](../explanation/architecture/data-model.md), [Security & Authorization](../explanation/architecture/security-and-authorization.md) |

---

## 1. Contexto e Declaração do Problema

A arquitetura anterior combinava coluna `organizacao_id` em 15 tabelas relacionais, políticas de Row-Level Security (`FORCE ROW LEVEL SECURITY`) com papel `medisync_app NOBYPASSRLS`, `ContextVar` transacional, `TenantResolutionMiddleware` (`X-Tenant-ID`, JWT claim `org_id` e subdomínio), chaves Valkey particionadas por `{org_id}` e bypass de `ADMIN_GLOBAL` entre tenants.

Contudo, o produto opera concretamente como uma **plataforma única** integrando cidadãos, médicos plantonistas e gestão operacional da unidade SUS, sem necessidade de hospedar múltiplos tenants isolados no mesmo banco. A sobrecarga de multi-tenancy espalhava `organizacao_id` por 27 endpoints HTTP, requests/responses, hooks de frontend (`getTenantHeaders`, `VITE_TENANT_ID`) e testes, sem agregar valor assistencial, enquanto enfraquecia a modelagem de segurança com papéis legados e desvios globais (`ADMIN_GLOBAL`).

---

## 2. Drivers de Decisão

* **Simplicidade Arquitetural & YAGNI**: Eliminar abstrações de multi-tenancy (`organizacoes`, `organizacao_id`, `X-Tenant-ID`, RLS, `TenantResolutionMiddleware`) em toda a pilha.
* **Segurança por Titularidade (Anti-IDOR + RBAC)**: Preservar e reforçar a proteção real de dados clínicos via RBAC estrito e checagem horizontal por titularidade (`paciente_id == usuario_id` / `medico_id` alocado), removendo qualquer bypass global cross-role (`ADMIN_GLOBAL`).
* **Preservação de Metadados SUS/ICP-Brasil**: Manter dados cadastrais da unidade (CNES, CNPJ, razão social, nome fantasia, código IBGE) para exportação BPA-I DATASUS e cabeçalhos PAdES-LTV / validação pública.
* **Compatibilidade Operacional com Legado de Storage**: Garantir leitura contínua de documentos já persistidos sob prefixos históricos no MinIO/S3 (`doc.chave_s3`).
* **Paridade com Stack Atômica**: Preservar fila Valkey ZSET + Lua (`alocar_chamada.lua`), ring timeout ARQ (45s), agenda GiST e conformidade CFM/LGPD.

---

## 3. Opções Consideradas

### Opção 1: Manter RLS com `MULTI_TENANCY_ENABLED=False`
* *Contras*: Conserva `organizacao_id` em 15 tabelas, políticas RLS, listeners `after_begin` com `SET LOCAL`, variáveis `DEFAULT_TENANT_ID` e cabeçalhos/claims redundantes em toda a API e frontend.

### Opção 2: Hardcode de metadados SUS em `.env`
* *Contras*: Viola ADR-009 (services acessando configuração) ou acopla relatórios BPA-I e PDFs ICP-Brasil a variáveis efêmeras fora do banco transacional.

### Opção 3: Plataforma Única Nativa com `ConfiguracaoUnidade` Singleton & Anti-IDOR Estrito (Adotada)
* *Prós*: Remoção completa de `organizacoes`, `organizacao_id`, RLS, `TenantResolutionMiddleware`, `X-Tenant-ID`, `ADMIN_GLOBAL` e `VITE_TENANT_ID`; consolidação limpa do schema em `migrations/versions/0001_initial_schema.py`; criação do singleton `configuracoes_unidade` (`ConfiguracaoUnidade`) com PK UUIDv7 + `singleton_guard`; RBAC enxuto em 4 papéis (`GESTOR_UNIDADE`, `MEDICO`, `FATURAMENTO`, `PACIENTE`).

---

## 4. Decisão

Adotamos a **Opção 3: Simplificação para Plataforma Única Nativa**.

### 4.1 Metadados da Unidade SUS (`ConfiguracaoUnidade`)
* A tabela `organizacoes` (`Organizacao`) é substituída pela tabela singleton **`configuracoes_unidade`** (`src/modules/identity/domain/models/configuracao_unidade.py:ConfiguracaoUnidade`), seguindo o padrão UUIDv7 da plataforma e restrição de linha única via `singleton_guard BOOLEAN` (`UniqueConstraint("singleton_guard")` + `CheckConstraint("singleton_guard IS TRUE", name="chk_configuracoes_unidade_singleton")`).
* Os adaptadores SQL `SqlBpaDirectory` (`ambulatory`) e `SqlDocumentDirectory` (`consultation`) consultam diretamente `configuracoes_unidade` (`cnpj`, `razao_social`, `nome_fantasia`, `cnes`, `ibge_municipio`, `tipo_unidade_sus`) para gerar BPA-I e PDFs ICP-Brasil, propagando também `cnpj` e `org_cnes = dir_data.cnes` em `DocumentoService.compilar_pdf`.

### 4.2 Consolidação Limpa do Banco e Remoção de RLS
* O histórico de migrações incrementais é consolidado em `migrations/versions/0001_initial_schema.py` contendo todas as 16 tabelas de Plataforma Única, extensão `btree_gist`, função `gen_uuidv7()` e trigger imutável `trg_prevent_audit_mutation` em `audit_events`.
* Removem-se todas as colunas `organizacao_id`, políticas `tenant_isolation_*`, `FORCE ROW LEVEL SECURITY`, papel `medisync_app NOBYPASSRLS`, listeners de sessão tenant em `src/core/database.py` e o módulo de contexto de tenant removido de `src/core/`.

### 4.3 RBAC Simplificado e Anti-IDOR sem Bypass Global
* `Role` (`src/core/authz/roles.py`) consolida exatamente 4 papéis: `GESTOR_UNIDADE`, `MEDICO`, `FATURAMENTO` e `PACIENTE` (removendo `ADMIN_GLOBAL` e papéis consorciais legados `GESTOR_CONSORCIO`, `REGULADOR_MUNICIPAL`, `AUDITOR_PRODUCAO`).
* `ROLES_REQUIRING_MFA` consolida `frozenset({"MEDICO", "GESTOR_UNIDADE"})`.
* `PapelProfissional` (`src/modules/identity/domain/models/profissional.py`) aceita `"GESTOR_UNIDADE"`, `"MEDICO"`, `"FATURAMENTO"`.
* `AtorPapel` (`src/core/audit/models.py`) mantém `PACIENTE`, `MEDICO`, `GESTOR_UNIDADE`, `FATURAMENTO`, `WORKER_ARQ`, `SISTEMA`.
* Remove-se integralmente qualquer bypass de `ADMIN_GLOBAL`; o acesso a dados clínicos permanece estritamente protegido por titularidade (**Anti-IDOR**: paciente acessa apenas seus atendimentos/documentos/dependentes/agendamentos; médico acessa consultas sob sua responsabilidade; gestor não acessa PEP médico).

### 4.4 HTTP, JWT, Valkey/Lua, LiveKit e Storage
* Removem-se `TenantResolutionMiddleware`, `X-Tenant-ID`, `TenantDep`, `OptionalTenantDep`, `TenantInvalidoError`, `MULTI_TENANCY_ENABLED`, `DEFAULT_TENANT_ID`, `VITE_TENANT_ID` e `getTenantHeaders`.
* Tokens JWT (`sub`, `papel`, `jti`) e `intake_token` deixam de emitir ou exigir `org_id`/`organizacao_id`.
* Chaves Valkey e scripts Lua passam a usar namespaces planos únicos: `fila:aptos`, `lock:medico:{id}`, `lock:atendimento:{id}`, `lock:consulta_ativa:medico:{id}`, `plantao:medicos_ativos`, `queue:admissoes:{data}`, `auth:ratelimit:{chave}` e `telemetry:painel`.
* Chaves S3 novas utilizam `build_signed_document_key` em `src/modules/consultation/domain/s3_keys.py` (`consultations/{atendimento_id}/documents/{documento_id}.pdf`), preservando a leitura direta de `doc.chave_s3` para artefatos preexistentes (`orgs/{id}/...`).

---

## 5. Consequências

### Positivas
* Redução drástica da superfície de código, assinaturas de serviços, contratos OpenAPI e hooks do frontend.
* Fim do risco de bypass administrativo horizontal com a eliminação de `ADMIN_GLOBAL`.
* Schema relacional limpo com índices B-Tree focados diretamente em chaves clínicas (`status`, `paciente_id`, `medico_id`, `identificador`, `cpf`, `cns`).

### Riscos Mitigados e Trade-offs
* **Escalabilidade futura em múltiplas unidades**: Caso venha a ser necessária segregação entre múltiplas unidades independentes, recomenda-se implantação isolada (banco/instância por unidade) em vez de reintroduzir multi-tenancy lógico no schema compartilhado.
* **Proteção horizontal**: Mitigada pela manutenção integral dos checkers de posse Anti-IDOR em `queue`, `consultation`, `identity`, `scheduling` e `auth`, testados continuamente em integração.
