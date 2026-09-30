# [ADR-007] Trilha de Auditoria Imutável Append-Only via DCL e Triggers Restritivas

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview](../03-architecture/overview.md), [Data Model](../03-architecture/data-model.md) (RN07, RNF-05) |

---

## 1. Contexto e Declaração do Problema

As normas médicas brasileiras (CFM nº 2.314/2022 e 1.821/2007) e o Art. 11 da LGPD estabelecem que qualquer intervenção, triagem, alteração de status, acesso ou emissão de receita em telemedicina deve possuir **trilha de auditoria perene, rastreável e imutável**. A plataforma precisa garantir que registros de auditoria jamais possam ser alterados ou expurgados, mesmo por usuários administrativos com credenciais da aplicação.

---

## 2. Drivers de Decisão

* **Imutabilidade Jurídica Estrita**: Impossibilidade física de mutação (`UPDATE`) ou deleção (`DELETE`) de eventos auditáveis.
* **Carimbo Temporal Universal**: Registro obrigatório de timestamps em formato UTC e hash criptográfico do TCLE aceito pelo paciente.
* **Consulta Rápida**: Facilidade de auditar a jornada completa de um atendimento em consultas relacionais indexadas.

---

## 3. Opções Consideradas

### Opção 1: Arquivos de Log em Disco (Plain Text / ELK Stack)
* *Prós*: Fácil de configurar com bibliotecas de logging.
* *Contras*: Risco de adulteração por operadores de sistema; dificuldade de vinculação relacional estrita com a transação clínica do banco; não previne falhas silenciosas.

### Opção 2: Event Sourcing Integral em Toda a Aplicação
* *Prós*: Histórico perfeito de todas as entidades.
* *Contras*: Complexidade arquitetural desproporcional; dificuldade de leitura para relatórios gerenciais e consultas transacionais ACID clássicas.

### Opção 3: Tabela Relacional `audit_events` com DCL e Trigger Restritiva no PostgreSQL (Adotada)
* *Prós*: Tabela normalizada indexada por `atendimento_id` e `registrado_em`. A blindagem é garantida na camada de banco: revogação formal de permissões (`REVOKE UPDATE, DELETE, TRUNCATE`) e criação de trigger `BEFORE UPDATE OR DELETE` disparando `RAISE EXCEPTION`. Qualquer tentativa de adulteração falha de forma ruidosa e imediata.
* *Contras*: Requer disciplina no gerenciamento de migrações que toquem na tabela de auditoria.

---

## 4. Decisão

Adotamos a **Opção 3: Trilha de Auditoria Append-Only no PostgreSQL com DCL e Trigger Restritiva**.

### Diretrizes de Execução:
1. Eventos gravados na tabela `audit_events` com chave primária em `UUIDv7`, contendo ator polimórfico (`UUID`), IP de origem, estados anterior/novo e hash do TCLE.
2. Geração de IDs na camada de aplicação via UUIDv7, eliminando a dependência de sequências de banco (`id_seq`) e garantindo inserções diretas sob DCL restrita sem falhas de permissão.
3. Triggers de banco ativas bloqueando qualquer mutação em tempo de execução via `RAISE EXCEPTION`.

---

## 5. Consequências

### Positivas:
* **Fidelidade Médico-Legal Inabalável**: Prova técnica irrefutável para defesas periciais e auditorias do CFM ou judiciais.
* **Integridade Transacional**: O registro de auditoria é gravado na mesma transação atômica (`session.commit()`) da ação clínica.
