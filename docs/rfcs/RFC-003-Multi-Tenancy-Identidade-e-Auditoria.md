# [RFC-003] Multi-Tenancy, Autenticação e Trilha Imutável de Auditoria

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Versão** | 1.0 |
| **Data** | 2026-09-13 |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (NEC-01, RN-REG-02, RN07, RNF-05, RT-01) |
| **RFC Base** | [RFC-001](RFC-001-Fundacao-Arquitetura-Base-e-Tooling.md), [RFC-002](RFC-002-Modelo-de-Dados-Agregados-e-Migracoes.md) |
| **Decisões de Arquitetura (ADRs)** | [ADR-003: Multi-Tenancy no ORM e RLS](../adrs/ADR-003-Multi-Tenancy-Logico-no-ORM.md), [ADR-004: Auditoria Append-Only](../adrs/ADR-004-Auditoria-Append-Only-Postgres-Rules.md), [ADR-010: Cadastro Progressivo e Identidade CFM](../adrs/ADR-010-Cadastro-Progressivo-e-Identidade-Clinica.md) |
| **Componentes Principais** | SQLAlchemy 2.0 Async, PostgreSQL 16 (RLS + DCL), Argon2id, JWT, RBAC |

---

## 1. Contexto & Requisitos de Isolamento e Segurança

O MediSync Express opera tanto em redes públicas municipais do SUS quanto em operadoras privadas e planos de autogestão. Tratando-se de dados sensíveis de saúde protegidos pelo Art. 11 da LGPD, a arquitetura deve atender a três pilares:
1. **Isolamento de Dados Inter-Tenant**: Garantia de que nenhum usuário ou consulta de uma organização acesse prontuários, triagens ou filas de outra instituição.
2. **Matriz de Acesso por Papel (RBAC) & Cadastro Progressivo**: Autenticação desenhada para cada persona, provendo acolhimento ágil sem paywall na primeira tela (< 45s) e enriquecimento cadastral obrigatório na fila de espera para conformidade com CFM nº 1.821/2007 e 2.314/2022 ([ADR-010](../adrs/ADR-010-Cadastro-Progressivo-e-Identidade-Clinica.md)).
3. **Trilha de Auditoria Imutável (Append-Only)**: Registro perene de todas as transições de estado clínico, carimbadas em UTC e blindadas contra alterações ou deleções no banco de dados (RN07, RNF-05).

---

## 2. Isolamento Multi-Tenant Transparente no ORM

Para viabilizar custos operacionais reduzidos em servidores modestos sem a sobrecarga de gerenciar milhares de bancos ou schemas físicos, adota-se o modelo de **multi-tenancy lógico por linha** (*discriminator column* `organizacao_id`), blindado nativamente no ciclo de vida do SQLAlchemy.

### 2.1 Propagação de Contexto via `ContextVar`
O ID do tenant é extraído do token JWT autenticado no middleware HTTP e armazenado em uma variável de contexto assíncrona (`ContextVar`), isolada por requisição:

```python
# src/core/context.py
from contextvars import ContextVar

tenant_context_var: ContextVar[int | None] = ContextVar("tenant_context_var", default=None)
```

### 2.2 Defesa em Profundidade: Interceptação no ORM + PostgreSQL Row-Level Security (RLS)

A proteção contra vazamento de dados entre organizações opera em duas camadas independentes e complementares:

#### Camada 1: Interceptação Automática no ORM (`do_orm_execute`)
Todas as consultas emitidas pelos repositórios recebem compulsoriamente a cláusula de filtro do tenant ativo, otimizando a query antes do envio à rede:

```python
# src/core/database.py
from sqlalchemy import event
from sqlalchemy.orm import Session
from src.core.context import tenant_context_var

@event.listens_for(Session, "do_orm_execute")
def interceptar_multi_tenant(execute_state):
    """
    Injeta automaticamente 'WHERE organizacao_id = :tenant_id' em consultas SELECT,
    UPDATE e DELETE, exceto quando explicitamente desativado para rotinas de sistema.
    """
    if not execute_state.execution_options.get("ignorar_tenant", False):
        org_id = tenant_context_var.get()
        if org_id is not None and execute_state.is_select:
            execute_state.statement = execute_state.statement.filter_by(organizacao_id=org_id)
```

#### Camada 2: Blindagem no Motor do Banco via PostgreSQL RLS Nativo
Para eliminar o risco residual de vazamento em consultas via SQL cru (`session.execute(text(...))`), inserções em massa ou joins complexos, o PostgreSQL 16 impõe **Row-Level Security (RLS)** nativo em todas as tabelas compartilhadas:

1. **Definição de Sessão**: No checkout da conexão / início de cada transação assíncrona, a sessão executa:
   ```python
   # Executado via listener ou middleware de sessão
   org_id = tenant_context_var.get()
   if org_id is not None:
       await session.execute(
           text("SET LOCAL app.current_tenant_id = :tenant_id"),
           {"tenant_id": str(org_id)}
       )
   ```

2. **Políticas de RLS no Banco de Dados**:
   ```sql
   ALTER TABLE atendimentos ENABLE ROW LEVEL SECURITY;
   ALTER TABLE atendimentos FORCE ROW LEVEL SECURITY;

   CREATE POLICY tenant_isolation_policy ON atendimentos
     USING (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint)
     WITH CHECK (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint);
   ```

Para tarefas do sistema que precisam varrer múltiplos tenants (como a reconciliação de filas no startup ou workers internos), utiliza-se o escape explícito:
```python
await session.execute(stmt, execution_options={"ignorar_tenant": True})
# A sessão de sistema também não define ou reseta app.current_tenant_id
```

---

## 3. Governança de Acesso, Autenticação e RBAC

A aplicação estabelece autenticação sob medida para cada persona do sistema, equilibrando agilidade de entrada em emergências com rigidez de segurança clínica:

| Papel de Acesso | Tabela / Entidade | Persona SRS | Mecanismo de Entrada | Credenciais & Fluxo |
| :--- | :--- | :--- | :--- | :--- |
| **`PACIENTE`** | `pacientes` | Juliana Silva | Cadastro Progressivo (OTP) | Validação cruzada (CPF/CNS + Data de Nascimento) + Código OTP (SMS/WhatsApp). Entrada em $< 45\text{ s}$ (Fase 1) e enriquecimento na fila (Fase 2) ([ADR-010](../adrs/ADR-010-Cadastro-Progressivo-e-Identidade-Clinica.md)). |
| **`MEDICO`** | `profissionais` | Dr. Eduardo Rocha | Credenciais Fortes + MFA | CRM/UF + E-mail + Senha com hash Argon2id + TOTP. Associação obrigatória a certificado ICP-Brasil (PREM-02). |
| **`FATURAMENTO`** | `profissionais` | Patrícia Mendes | Login Institucional | E-mail corporativo + Senha com auditoria de acesso aos dados de operadoras e convênios. |
| **`GESTOR_UNIDADE`** | `profissionais` | Carlos Drumond | Login Corporativo + MFA | E-mail + Senha + TOTP. Parametrização de SLAs, cotas e fator de backpressure $\alpha$ da unidade (RF-09). |
| **`ADMIN_GLOBAL`** | `profissionais` | Time DevOps | SSO Corporativo / API Key | Acesso restrito a IPs autorizados para manutenção da plataforma e criação de tenants. |

### 3.1 Pipeline de Cadastro Progressivo e Identidade Clínica (CFM e LGPD)

Em conformidade com as Resoluções CFM nº 1.821/2007 e 2.314/2022 e a [ADR-010](../adrs/ADR-010-Cadastro-Progressivo-e-Identidade-Clinica.md), o cadastro do paciente é estruturado em duas fases para conciliar urgência clínica com validade jurídica:

#### Fase 1: Fast-Track de Acolhimento e Triagem (< 45s)
- **Vínculo do Atendimento**: O titular declara se a consulta é para `MIM_MESMO` ou `DEPENDENTE` (permitindo que pais atendam filhos menores que não possuem celular).
- **Validação Anti-Fraude Primária**: Cruzamento obrigatório de `CPF` (ou titular) e `Data de Nascimento`. Evita que terceiros digitem documentos alheios para tentar espionar prontuários via OTP.
- **Proteção Anti-Abuso (Rate Limiting)**: O envio de códigos OTP é limitado no Valkey a no máximo 3 solicitações por telefone/IP a cada 10 minutos.
- **Triagem e TCLE**: Coleta de sintomas agudos e outorga do TCLE (pelo paciente ou seu responsável legal), inserindo o atendimento na fila com status `TRIADO_AGUARDANDO_ELEGIBILIDADE`.

#### Fase 2: Enriquecimento Cadastral Obrigatório na Fila de Espera
Enquanto aguarda a alocação médica na fila dinâmica, o paciente preenche os dados exigidos pelo CFM:
1. **Identificação Civil**: Nome completo, nome social (se houver), sexo biológico e nome da mãe (chave de desambiguação universal no CADSUS e Receita Federal).
2. **Endereço Completo com CEP**: Autopreenchido via integração de CEP. **Mandatório** para que o médico plantonista possua a localização exata caso precise acionar resgate de emergência via SAMU 192, além de ser obrigatório na emissão de receituários digitais.
3. **Segurança Farmacológica**: Histórico obrigatório de alergias medicamentosas conhecidas (`dipirona`, `amoxicilina/penicilinas`, `AINEs`, etc.) e medicamentos de uso contínuo, exibidos em destaque de alerta no prontuário do médico.
4. **Habilitação de Chamada**: O atendimento só atinge o status `APTO_PARA_CHAMADA` quando a validação de elegibilidade e o enriquecimento cadastral estiverem concluídos.

### 3.2 Guardas de Autorização no FastAPI (`dependencies.py`)

A checagem de permissões é declarativa através de dependências combinadas:

```python
# src/modules/identidade/dependencies.py
from typing import Annotated
from fastapi import Depends, HTTPException, status
from src.modules.identidade.models import PapelProfissional

def exigir_papeis(*papeis_permitidos: PapelProfissional):
    """Guarda RBAC para autorização de endpoints da equipe profissional."""
    def verificador_permissao(
        profissional: Annotated[ContextoProfissional, Depends(obter_profissional_logado)]
    ) -> ContextoProfissional:
        if profissional.papel not in papeis_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso não autorizado para o papel do profissional."
            )
        return profissional
    return verificador_permissao
```

---

## 4. Trilha de Auditoria Imutável (Append-Only)

A Resolução CFM nº 2.314/2022 e a LGPD exigem que toda transição de estado clínico e aceite de termo seja perfeitamente rastreável e inviolável.

### 4.1 Estrutura da Tabela `audit_events`

```sql
CREATE TABLE audit_events (
    id BIGSERIAL PRIMARY KEY,
    organizacao_id BIGINT NOT NULL REFERENCES organizacoes(id),
    atendimento_id BIGINT NOT NULL REFERENCES atendimentos(id),
    ator_tipo VARCHAR(20) NOT NULL, -- 'PROFISSIONAL', 'PACIENTE', 'SISTEMA'
    ator_id BIGINT,                 -- ID na tabela profissionais ou pacientes
    ator_papel VARCHAR(32) NOT NULL,-- 'PACIENTE', 'MEDICO', 'GESTOR_UNIDADE', 'FATURAMENTO', 'WORKER_ARQ'
    tipo_evento VARCHAR(64) NOT NULL,
    estado_anterior VARCHAR(32),
    novo_estado VARCHAR(32),
    tcle_hash CHAR(64),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_origem INET,
    registrado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);
```

### 4.2 Blindagem Anti-Adulteração via Permissões DCL e Triggers com `RAISE EXCEPTION`

Para assegurar imutabilidade estrita conforme o CFM nº 2.314/2022 e o Art. 11 da LGPD, adotam-se duas barreiras ativas no PostgreSQL 16, evitando as falhas silenciosas de regras antigas (`CREATE RULE ... DO INSTEAD NOTHING`):

1. **Princípio do Menor Privilégio (DCL)**: O usuário da aplicação (`medisync_app`) tem privilégios de mutação explicitamente revogados no banco de dados:
   ```sql
   REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM PUBLIC, medisync_app;
   GRANT SELECT, INSERT ON audit_events TO medisync_app;
   ```

2. **Trigger Restritiva com Falha Explícita (Fail-Fast)**: Caso qualquer instrução de alteração ou exclusão seja enviada, o PostgreSQL aborta a transação imediatamente com código de erro específico (`restrict_violation`), impedindo mutações silenciosas:
   ```sql
   CREATE OR REPLACE FUNCTION trg_prevent_audit_mutation()
   RETURNS TRIGGER AS $$
   BEGIN
       RAISE EXCEPTION 'A tabela audit_events é estritamente append-only (CFM 2.314/2022 e LGPD Art. 11). Operações de UPDATE ou DELETE são proibidas.'
           USING ERRCODE = 'restrict_violation';
   END;
   $$ LANGUAGE plpgsql;

   CREATE TRIGGER trg_audit_events_immutable
   BEFORE UPDATE OR DELETE ON audit_events
   FOR EACH ROW EXECUTE FUNCTION trg_prevent_audit_mutation();
   ```

Essa abordagem garante que:
- Qualquer tentativa acidental ou maliciosa de modificar ou apagar logs gere exceção de banco de dados visível na telemetria, sem mascarar falhas da aplicação com `rowcount = 0`.
- O hash SHA-256 do Termo de Consentimento Livre e Esclarecido (TCLE) permaneça indelevelmente registrado no histórico probatório.

---

## 5. Decisões Arquiteturais Relacionadas (ADRs)

A justificativa técnica e a análise comparativa de isolamento multi-tenant, imutabilidade de banco de dados e onboarding progressivo estão registradas formalmente em:
- **[ADR-003: Multi-Tenancy Lógico por Linha com Interceptação no ORM](../adrs/ADR-003-Multi-Tenancy-Logico-no-ORM.md)**
- **[ADR-004: Trilha de Auditoria Imutável (Append-Only) via PostgreSQL Rules](../adrs/ADR-004-Auditoria-Append-Only-Postgres-Rules.md)**
- **[ADR-010: Cadastro Progressivo em Duas Etapas e Identificação Clínica Segura](../adrs/ADR-010-Cadastro-Progressivo-e-Identidade-Clinica.md)**
