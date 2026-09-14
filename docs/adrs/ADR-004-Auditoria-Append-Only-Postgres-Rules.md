# [ADR-004] Trilha de Auditoria Imutável (Append-Only) via PostgreSQL Rules

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RN07, RNF-05) |

---

## 1. Contexto e Declaração do Problema

A Resolução CFM nº 2.314/2022 e a LGPD (Art. 11) impõem que o histórico clínico e o consentimento explícito do paciente (TCLE) possuam rastreabilidade perene e valor probatório irrefutável.

Se registros de auditoria puderem ser alterados ou deletados (por falhas de aplicação, credenciais de banco vazadas ou agentes mal-intencionados), a instituição fica juridicamente exposta em litígios e processos ético-profissionais. Precisamos de um mecanismo que garanta que, uma vez gravado, o evento de auditoria seja estritamente **imutável e perene**.

---

## 2. Drivers de Decisão

- **Imutabilidade Jurídica Estrita**: Impossibilidade de adulteração ou exclusão de eventos passados (RN07).
- **Vínculo Criptográfico do Consentimento**: Preservação do hash SHA-256 do TCLE aceito pelo paciente em cada marco de atendimento.
- **Independência da Camada de Aplicação**: A garantia de imutabilidade deve ser imposta pelo próprio motor do banco de dados relacional.

---

## 3. Opções Consideradas

### Opção 1: Logs de Aplicação Externos (Elasticsearch / CloudWatch / OpenSearch)
Enviar eventos de auditoria formatados em JSON para um agregador de logs.
- *Prós*: Separação física dos dados transacionais.
- *Contras*: Alto custo operacional de manter um cluster de logs; dificuldade de correlacionar eventos com chaves estrangeiras (`FOREIGN KEY`) do banco relacional; políticas de expiração de logs (retenção padrão de 30 a 90 dias) incompatíveis com a guarda médica de 20 anos do CFM.

### Opção 2: Shadow Tables com Triggers de Auditoria
Manter a tabela original e usar *database triggers* para copiar registros anteriores para uma tabela de histórico quando ocorrerem updates.
- *Prós*: Padrão conhecido no ecossistema PostgreSQL.
- *Contras*: Triggers ainda permitem a exclusão manual se um usuário com permissões de escrita rodar comandos `DELETE` na tabela de histórico; alto overhead computacional em tabelas de alto volume.

### Opção 3: Imutabilidade via PostgreSQL Rules (`CREATE RULE ... DO INSTEAD NOTHING`)
Interceptar comandos `UPDATE` e `DELETE` no motor do banco através de regras de reescrita do catálogo.
- *Prós*: Impede a mutação sem alterar a estrutura da tabela.
- *Contras*: Feature legada do PostgreSQL; suprime silenciosamente operações retornando contagem de linhas zerada (`rowcount = 0`), mascarando erros da aplicação e falhando em notificar violações com exceções explícitas; efeitos colaterais com `RETURNING` e CTEs.

### Opção 4: Trilha Append-Only com Permissões Restritas (DCL) e Trigger com `RAISE EXCEPTION`
Combinar o princípio do menor privilégio no usuário da aplicação com uma trigger restritiva que rejeita com erro fatal qualquer tentativa de mutação:
1. **DCL (Data Control Language)**: Revogar permissões de mutação do papel da aplicação: `REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM medisync_app;`
2. **Trigger Restritiva**: Trigger `BEFORE UPDATE OR DELETE` que executa função PL/pgSQL disparando `RAISE EXCEPTION ... USING ERRCODE = 'restrict_violation'`.
- *Prós*: Prática padrão moderna no PostgreSQL 16; falha rápida e explícita (fail-fast), gerando erro imediato na aplicação em vez de comportamento silencioso; conformidade jurídica estrita com CFM 2.314/2022 e LGPD Art. 11.
- *Contras*: Requer definição de privilégios de banco nos scripts de migração do Alembic.

---

## 4. Decisão

Adotamos a **Opção 4: Trilha Append-Only com Permissões Restritas (DCL) e Trigger com `RAISE EXCEPTION`**.

### Diretrizes de Execução:
1. **Estrutura de Registro**: Cada transição registra: `organizacao_id`, `atendimento_id`, `ator_id`, `ator_papel`, `tipo_evento`, `estado_anterior`, `novo_estado`, `tcle_hash`, `payload` (JSONB), `ip_origem` e `registrado_em` (UTC).
2. **Revogação de Privilégios no Banco**:
   ```sql
   REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM PUBLIC, medisync_app;
   GRANT SELECT, INSERT ON audit_events TO medisync_app;
   ```
3. **Trigger de Proteção Ativa com Exceção Explícita**:
   ```sql
   CREATE OR REPLACE FUNCTION trg_prevent_audit_mutation()
   RETURNS TRIGGER AS $$
   BEGIN
       RAISE EXCEPTION 'A tabela audit_events é estritamente append-only (CFM 2.314/2022 e LGPD Art. 11). Operações de UPDATE ou DELETE são terminantemente proibidas.'
           USING ERRCODE = 'restrict_violation';
   END;
   $$ LANGUAGE plpgsql;

   CREATE TRIGGER trg_audit_events_immutable
   BEFORE UPDATE OR DELETE ON audit_events
   FOR EACH ROW EXECUTE FUNCTION trg_prevent_audit_mutation();
   ```
4. **Versionamento com Alembic**: A criação da tabela, da trigger e a revogação de privilégios são aplicadas atomicamente na migração inicial.

---

## 5. Consequências

### Positivas:
- **Blindagem Jurídica Total**: A integridade dos dados históricos está protegida contra erros da aplicação ou invasões no nível de privilégio da aplicação.
- **Rastreabilidade Instantânea**: Consultas periciais sobre o ciclo de vida do paciente são resolvidas com queries SQL simples.

### Negativas / Riscos Mitigados:
- *Crescimento da Tabela*: Como não há deleção, a tabela cresce continuamente. Mitigado por particionamento futuro por ano/trimestre (`PARTITION BY RANGE (registrado_em)`) caso o volume atinja dezenas de milhões de linhas.
