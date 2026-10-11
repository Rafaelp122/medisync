# Identity Domain

> Cadastro de pacientes com CPF/CNS, nome social mandatório (CFM 1.821/2007), dependentes vinculados, profissionais com CRM/UF, isolamento por RLS via organizacao_id.

## 1. Contexto e Conformidade Regulatória

O domínio de Identidade gerencia o ciclo cadastral de pacientes e profissionais de saúde.
Em estrita conformidade com a **Resolução CFM 1.821/2007** e diretrizes do SUS/MS, o sistema assegura o registro e exibição destacada do **nome social** (`nome_social`), garantindo dignidade ao paciente e integridade do prontuário eletrônico.

## 2. Regras de Negócio e Cadastro

- **Nome Social:** Campo opcional no cadastro, porém mandatório na identificação visual e documentos clínicos quando preenchido.
- **Isolamento Multitenant:** Pacientes e profissionais são particionados por `organizacao_id` via PostgreSQL Row-Level Security (RLS).
- **Onboarding em 2 Fases:**
  - Fase 1: Coleta de credenciais de acesso e criação da conta de usuário.
  - Fase 2: Qualificação civil (CPF, CNS, data de nascimento, telefone e `nome_social`).

## 3. Onde no código

- `src/modules/identity/domain/models/paciente.py` (Modelo Paciente com coluna e atributo `nome_social`)
- `src/modules/identity/application/dtos.py` (DTOs `Fase1InputDTO`, `Fase2InputDTO`, `Fase2OutputDTO`)
- `src/modules/identity/application/services/onboarding_service.py` (Serviço de onboarding propagando `nome_social`)
- `src/modules/identity/presentation/schemas.py` (Schemas `Fase1Request`, `Fase2Request`, `Fase2Response`)
- `src/modules/identity/infrastructure/identity_reader_sql.py` (Reader port mapeando `paciente_nome_social`)
- `migrations/versions/0005_paciente_nome_social.py` (Migration Alembic adicionando coluna na tabela `pacientes`)
- `tests/unit/test_identity_models.py` (Testes unitários de instanciação do modelo)
- `tests/unit/test_onboarding_schemas.py` (Testes unitários de validação e serialização de schemas)

## 4. Ver também

- [Product Specification](../product-specification.md) — RF-01 e conformidade CFM
- [Data Model](../architecture/data-model.md) — tabela `pacientes`
- [Domains Index](./index.md) — visão conceitual por domínio
