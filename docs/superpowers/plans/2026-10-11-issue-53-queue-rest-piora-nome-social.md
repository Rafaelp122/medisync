# Issue #53: Endpoints REST da Fila, Cota Diária, Salvaguarda de Piora e Nome Social

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar os endpoints REST da fila virtual (`/fila/chamar-proximo`, `/fila/posicao/{id}`, `/fila/cancelar/{id}`, `/fila/piora`), corrigir a verificação e incremento da cota diária no Valkey (RN05), adicionar suporte mandatório a `nome_social` no modelo `Paciente` e schemas (CFM 1.821/2007) com migration Alembic, e atualizar todas as documentações correlatas.

**Architecture:** Hexagonal Pragmático estrito sem Mapper Hell (ADR-001/ADR-008). Routers finos validados por AST sem imports proibidos (`test_routers_are_thin.py`), transação única nos services (`await session.commit()`), contratos tipados via DTOs/Schemas Pydantic v2 `from_attributes=True`, isolamento de fronteiras com `tach check` e validação de documentação com `scripts/docs_check.py`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 (async), Alembic, Valkey 8.0 (Redis client), Pydantic v2, pytest-asyncio, basedpyright (strict), tach.

---

## Análise Crítica da Issue #53 (Diagnóstico de Conformidade)

A inspeção detalhada do código-fonte confirmou que **todos os problemas apontados na Issue #53 são reais e estão presentes no repositório**:

1. **NC-QUE-01 (Bypass da Cota Diária no Backpressure)**:
   - **Evidência**: Em [`src/modules/queue/application/services/admissao_service.py:77`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/admissao_service.py#L77), `total_admissoes_hoje=0` é passado hardcoded ao `AvaliarAdmissaoCommand`. Além disso, após a persistência da admissão, o método `incrementar_admissoes_hoje` de `ControleAdmissaoService` nunca é invocado.
   - **Impacto**: A Condição A da regra RN05 (`total_admissoes_hoje >= cota_diaria_maxima`) nunca bloqueia novas admissões, violando o controle de capacidade do plantão.

2. **NC-QUE-02 e NC-MED-02 (Ausência de Routers REST da Fila e Salvaguarda de Piora)**:
   - **Evidência**: O diretório [`src/modules/queue/presentation/routers/`](file:///home/rafael/projetos/medisync/src/modules/queue/presentation/routers/) contém apenas `admissao_router.py` e `queue_ws_router.py`. Não existem rotas HTTP para:
     - Médico solicitar próximo paciente (`POST /fila/chamar-proximo`, RF-03);
     - Paciente consultar posição e estimativa de espera via REST (`GET /fila/posicao/{atendimento_id}`);
     - Paciente desistir/cancelar atendimento antes da consulta (`POST /fila/cancelar/{atendimento_id}`, RN06);
     - Paciente acionar o botão de piora de sintomas na espera (`POST /fila/piora`, RF-06).
   - **Impacto**: Interações essenciais do médico e do paciente dependiam de chamadas diretas aos services ou estavam inacessíveis via API REST.

3. **NC-REG-01 (Inexistência de Nome Social no Paciente)**:
   - **Evidência**: [`src/modules/identity/domain/models/paciente.py`](file:///home/rafael/projetos/medisync/src/modules/identity/domain/models/paciente.py) não possui a coluna/atributo `nome_social`. A tabela `pacientes` não contém a coluna correspondente, e os schemas de Fase 1 e 2 (`Fase1Request`, `Fase2Request`, `Fase2Response`, DTOs) omitem o campo.
   - **Impacto**: Violação direta da Resolução CFM nº 1.821/2007 e portarias de humanização e acolhimento do SUS.

---

## Estrutura de Arquivos Afetados

```
migrations/versions/
└── 0005_paciente_nome_social.py                       [NOVO] Migration Alembic para coluna nome_social

src/modules/identity/
├── domain/models/paciente.py                          [MODIFICA] Adiciona nome_social: Mapped[str | None]
├── application/dtos.py                                [MODIFICA] Adiciona nome_social em DTOs de Fase 1, 2 e Reader
├── application/ports/identity_reader_port.py          [MODIFICA] Adiciona paciente_nome_social em IdentityDirectoryDTO
├── application/services/onboarding_service.py         [MODIFICA] Propaga nome_social na Fase 1 e Fase 2
├── infrastructure/identity_reader_sql.py              [MODIFICA] Mapeia pac.nome_social em IdentityDirectoryDTO
└── presentation/schemas.py                            [MODIFICA] Adiciona nome_social em Fase1Request, Fase2Request e Fase2Response

src/modules/queue/
├── application/dtos.py                                [MODIFICA] DTOs de chamada, posição, cancelamento e piora clínica
├── application/services/admissao_service.py           [MODIFICA] Lê e incrementa cota diária no Valkey (NC-QUE-01)
├── application/services/fila_service.py               [MODIFICA] Métodos para posição/estimativa, cancelamento e piora
├── presentation/schemas.py                            [MODIFICA] Schemas Pydantic v2 para os 4 novos endpoints
├── presentation/dependencies.py                       [MODIFICA] Guards de posse de atendimento e papel médico
├── presentation/routers/
│   ├── __init__.py                                    [MODIFICA] Exporta novos routers
│   ├── alocacao_router.py                             [NOVO] POST /fila/chamar-proximo
│   └── fila_router.py                                 [NOVO] GET /posicao, POST /cancelar, POST /piora
└── composition.py                                     [MODIFICA] Injeta TriagePort em FilaService para reavaliação de piora

src/main.py                                            [MODIFICA] Registra alocacao_router e fila_router no prefixo /api/v1

docs/
├── auditoria_completa_sistema.md                      [MODIFICA] Atualiza status de NCs para [SANEADO]
├── explanation/domains/queue-domain.md                [MODIFICA] Documenta novos endpoints e cota atômica
├── explanation/domains/identity-domain.md             [MODIFICA] Documenta conformidade de nome social (CFM/SUS)
└── explanation/product-specification.md               [MODIFICA] Mapeia endpoints REST em RF-03 e RF-06

tests/
├── unit/test_identity_models.py                       [MODIFICA] Testa suporte e validações de nome_social
├── unit/test_onboarding_service.py                    [MODIFICA] Testa persistência de nome_social nas Fases 1 e 2
├── unit/test_queue_cota_diaria.py                     [NOVO] Testa backpressure por cota no Valkey
├── unit/test_fila_service_operacoes.py                [NOVO] Testa posição, cancelamento e piora clínica
├── unit/test_alocacao_router.py                       [NOVO] Testa POST /fila/chamar-proximo
└── unit/test_fila_router.py                           [NOVO] Testa /posicao, /cancelar e /piora
```

---

## Tarefas de Implementação

### Tarefa 1: Suporte a Nome Social no Modelo Paciente e Migration (NC-REG-01)

**Files:**
- Create: `migrations/versions/0005_paciente_nome_social.py`
- Modify: `src/modules/identity/domain/models/paciente.py`
- Modify: `tests/factories/identity.py`
- Modify: `tests/unit/test_identity_models.py`

- [ ] **Passo 1: Escrever teste unitário para o atributo `nome_social` no modelo `Paciente`**

Editar `tests/unit/test_identity_models.py` adicionando teste para verificar sanitização e atribuição de `nome_social`:
```python
def test_paciente_com_nome_social_succeeds():
    paciente = Paciente(
        organizacao_id=1,
        cpf="12345678901",
        data_nascimento=date(1990, 5, 20),
        nome_completo="Carlos Silva",
        nome_social="Carla Silva",
        telefone="11999998888",
    )
    assert paciente.nome_social == "Carla Silva"
    assert paciente.nome_completo == "Carlos Silva"
```

- [ ] **Passo 2: Rodar o teste e verificar que falha**

Run: `uv run pytest tests/unit/test_identity_models.py::test_paciente_com_nome_social_succeeds`
Expected: FAIL com `TypeError: Paciente.__init__() got an unexpected keyword argument 'nome_social'`

- [ ] **Passo 3: Atualizar o modelo `Paciente` e a factory de testes**

Em `src/modules/identity/domain/models/paciente.py`:
- Adicionar coluna:
  ```python
  nome_social: Mapped[str | None] = mapped_column(String(255), nullable=True)
  ```
- No construtor `__init__`, adicionar `nome_social: str | None = None` e tratar `nome_social.strip() if nome_social else None`.
- Em `tests/factories/identity.py`, adicionar `nome_social: str | None = None` no `make_paciente`.

- [ ] **Passo 4: Criar migration Alembic `0005_paciente_nome_social.py`**

Criar arquivo `migrations/versions/0005_paciente_nome_social.py`:
```python
"""Add nome_social column to pacientes table for CFM 1.821/2007 compliance.

Revision ID: 0005_paciente_nome_social
Revises: 0004_evolucao_finalizado_em
Create Date: 2026-10-11 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_paciente_nome_social"
down_revision: str | None = "0004_evolucao_finalizado_em"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pacientes",
        sa.Column("nome_social", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pacientes", "nome_social")
```

- [ ] **Passo 5: Rodar testes unitários do modelo e checar aprovação**

Run: `uv run pytest tests/unit/test_identity_models.py`
Expected: PASS

- [ ] **Passo 6: Commit**

```bash
git add migrations/versions/0005_paciente_nome_social.py src/modules/identity/domain/models/paciente.py tests/factories/identity.py tests/unit/test_identity_models.py
git commit -m "feat(identity): adicionar campo nome_social no modelo Paciente e migration CFM 1.821/2007"
```

---

### Tarefa 2: Propagação de Nome Social nos DTOs, Schemas, OnboardingService e Reader

**Files:**
- Modify: `src/modules/identity/application/dtos.py`
- Modify: `src/modules/identity/application/ports/identity_reader_port.py`
- Modify: `src/modules/identity/infrastructure/identity_reader_sql.py`
- Modify: `src/modules/identity/application/services/onboarding_service.py`
- Modify: `src/modules/identity/presentation/schemas.py`
- Modify: `tests/unit/test_onboarding_service.py`

- [ ] **Passo 1: Escrever teste de onboarding para verificar persistência e retorno de `nome_social`**

Adicionar teste em `tests/unit/test_onboarding_service.py`:
- Submeter Fase 1 com `nome_social="Carla Silva"`.
- Validar que o paciente é persistido com `nome_social` preenchido.
- Submeter Fase 2 e verificar que `Fase2Response` retorna `nome_social`.

- [ ] **Passo 2: Rodar o teste e verificar que falha**

Run: `uv run pytest tests/unit/test_onboarding_service.py`
Expected: FAIL

- [ ] **Passo 3: Atualizar DTOs e Portas de Identidade**

Em `src/modules/identity/application/dtos.py`:
- `Fase1InputDTO`: adicionar `nome_social: str | None = None`.
- `Fase2InputDTO`: adicionar `nome_social: str | None = None`.
- `Fase2OutputDTO`: adicionar `nome_social: str | None = None`.
- `IdentityDirectoryDTO` em `src/modules/identity/application/ports/identity_reader_port.py`: adicionar `paciente_nome_social: str | None = None`.
- `SqlIdentityReader` em `src/modules/identity/infrastructure/identity_reader_sql.py`: repassar `paciente_nome_social=pac.nome_social`.

- [ ] **Passo 4: Atualizar Schemas Pydantic de Apresentação**

Em `src/modules/identity/presentation/schemas.py`:
- `Fase1Request`: adicionar `nome_social: str | None = Field(default=None, max_length=255, description="Nome social do paciente (CFM 1.821/2007 e SUS)")`.
- `Fase2Request`: adicionar `nome_social: str | None = Field(default=None, max_length=255, description="Nome social do paciente (CFM 1.821/2007 e SUS)")`.
- `Fase2Response`: adicionar `nome_social: str | None = None`.

- [ ] **Passo 5: Atualizar `OnboardingService`**

Em `src/modules/identity/application/services/onboarding_service.py`:
- Na Fase 1: se novo paciente, passar `nome_social=dados.nome_social.strip() if dados.nome_social else None`. Se existente, atualizar se fornecido.
- Na Fase 2: se `dados.nome_social` fornecido, atualizar `paciente.nome_social = dados.nome_social.strip()`. Preencher `Fase2OutputDTO(..., nome_social=paciente.nome_social)`.

- [ ] **Passo 6: Rodar testes e verificar aprovação**

Run: `uv run pytest tests/unit/ -k onboarding`
Expected: PASS

- [ ] **Passo 7: Commit**

```bash
git add src/modules/identity/ tests/
git commit -m "feat(identity): suportar nome_social nos schemas, DTOs, onboarding e reader"
```

---

### Tarefa 3: Leitura e Incremento Atômico da Cota Diária no Valkey (NC-QUE-01 / RN05)

**Files:**
- Modify: `src/modules/queue/application/services/admissao_service.py`
- Modify: `src/modules/queue/application/services/controle_admissao_service.py`
- Create: `tests/unit/test_queue_cota_diaria.py`

- [ ] **Passo 1: Escrever teste unitário para controle de cota diária no Valkey**

Criar `tests/unit/test_queue_cota_diaria.py`:
- Testar que `admitir_paciente` consulta `obter_admissoes_hoje(organizacao_id)`.
- Testar que se `total_admissoes_hoje >= cota_diaria_maxima`, a admissão é rejeitada com `AdmissaoFilaSuspensaError(motivo="COTA_ATINGIDA")`.
- Testar que em caso de sucesso na admissão, `incrementar_admissoes_hoje(organizacao_id)` é chamado no Valkey.

- [ ] **Passo 2: Rodar o teste e verificar que falha**

Run: `uv run pytest tests/unit/test_queue_cota_diaria.py`
Expected: FAIL (pois `total_admissoes_hoje=0` é fixo e o incremento não é executado)

- [ ] **Passo 3: Integrar leitura e incremento da cota em `AdmissaoAtendimentoService`**

Em `src/modules/queue/application/services/admissao_service.py`:
- Antes de avaliar a admissão:
  ```python
  admissoes_hoje = await self._controle_admissao.obter_admissoes_hoje(command.organizacao_id)
  ```
- Passar `total_admissoes_hoje=admissoes_hoje` para o `AvaliarAdmissaoCommand`.
- Após persistir e commitar o atendimento (`await self._session.commit()`):
  ```python
  await self._controle_admissao.incrementar_admissoes_hoje(command.organizacao_id)
  ```
- Assegurar chave padronizada no Valkey em `ControleAdmissaoService`: `f"queue:admissoes:{organizacao_id}:{today}"` com TTL de 48h.

- [ ] **Passo 4: Rodar o teste e verificar que passa**

Run: `uv run pytest tests/unit/test_queue_cota_diaria.py`
Expected: PASS

- [ ] **Passo 5: Commit**

```bash
git add src/modules/queue/application/services/admissao_service.py src/modules/queue/application/services/controle_admissao_service.py tests/unit/test_queue_cota_diaria.py
git commit -m "fix(queue): integrar leitura e incremento da cota diária no Valkey (NC-QUE-01 / RN05)"
```

---

### Tarefa 4: Métodos de Aplicação para Posição, Cancelamento e Piora Clínica em `FilaService`

**Files:**
- Modify: `src/modules/queue/application/dtos.py`
- Modify: `src/modules/queue/application/services/fila_service.py`
- Modify: `src/modules/queue/composition.py`
- Create: `tests/unit/test_fila_service_operacoes.py`

- [ ] **Passo 1: Definir DTOs de aplicação em `src/modules/queue/application/dtos.py`**

Adicionar:
- `PosicaoFilaResult(atendimento_id: UUID, status: str, posicao: int | None, total_aguardando: int, tempo_estimado_segundos: int | None)`
- `CancelarAtendimentoResult(atendimento_id: UUID, status: str, cancelado_em: datetime, motivo: str | None)`
- `PioraClinicaCommand(organizacao_id: int, atendimento_id: UUID, novos_sintomas: list[str], escala_dor: int = 0, queixa_adicional: str = "")`
- `PioraClinicaResult(atendimento_id: UUID, prioridade_clinica: int, alerta_samu_disparado: bool, redirecionado_emergencia: bool, nova_posicao: int | None, instrucoes: str | None)`

- [ ] **Passo 2: Escrever testes unitários para as operações de fila**

Criar `tests/unit/test_fila_service_operacoes.py`:
- Testar `obter_posicao_e_estimativa` para paciente em fila ZSET.
- Testar `cancelar_atendimento_paciente` removendo do ZSET e transicionando status para `CANCELADO_PACIENTE`.
- Testar `processar_piora_clinica`:
  - Caso SAMU (Nível 1): atendimento cancelado/desviado, removido da fila, `alerta_samu_disparado=True`.
  - Caso Reclassificação (ex: de Nível 4 para Nível 2): prioridade atualizada, novo score calculado e ZSET atualizado.

- [ ] **Passo 3: Rodar os testes e verificar que falham**

Run: `uv run pytest tests/unit/test_fila_service_operacoes.py`
Expected: FAIL com métodos não encontrados no `FilaService`

- [ ] **Passo 4: Implementar métodos em `FilaService`**

Em `src/modules/queue/application/services/fila_service.py`:
- Adicionar `triage_port: TriagePort | None = None` no `__init__`.
- Implementar:
  1. `obter_posicao_e_estimativa(organizacao_id: int, atendimento_id: UUID) -> PosicaoFilaResult`
  2. `cancelar_atendimento_paciente(organizacao_id: int, atendimento_id: UUID, motivo: str | None = None) -> CancelarAtendimentoResult`
  3. `processar_piora_clinica(command: PioraClinicaCommand) -> PioraClinicaResult`
- Garantir que cada método que altera estado persiste com `await self._db_session.commit()`.

- [ ] **Passo 5: Atualizar composition root de `queue`**

Em `src/modules/queue/composition.py`:
- Injetar `TriagePort` em `build_fila_service_for_session` e `get_fila_service` via `TriageServiceDep`.

- [ ] **Passo 6: Rodar os testes e verificar que passam**

Run: `uv run pytest tests/unit/test_fila_service_operacoes.py`
Expected: PASS

- [ ] **Passo 7: Commit**

```bash
git add src/modules/queue/application/ src/modules/queue/composition.py tests/unit/test_fila_service_operacoes.py
git commit -m "feat(queue): implementar logica de aplicacao para posicao, cancelamento e piora clinica"
```

---

### Tarefa 5: Schemas Pydantic, Dependencies e Routers Finos REST da Fila (NC-QUE-02 e NC-MED-02)

**Files:**
- Modify: `src/modules/queue/presentation/schemas.py`
- Modify: `src/modules/queue/presentation/dependencies.py`
- Create: `src/modules/queue/presentation/routers/alocacao_router.py`
- Create: `src/modules/queue/presentation/routers/fila_router.py`
- Modify: `src/modules/queue/presentation/routers/__init__.py`
- Modify: `src/main.py`
- Create: `tests/unit/test_alocacao_router.py`
- Create: `tests/unit/test_fila_router.py`

- [ ] **Passo 1: Criar schemas Pydantic v2 em `src/modules/queue/presentation/schemas.py`**

Adicionar com `model_config = ConfigDict(from_attributes=True, frozen=True)`:
- `ChamarProximoRequest(ttl_segundos: int = 45)`
- `ChamarProximoResponse(alocado: bool, atendimento_id: UUID | None, medico_id: UUID | None, status: str | None, chamada_iniciada_em: datetime | None, ttl_segundos: int = 45, mensagem: str | None = None)`
- `PosicaoFilaResponse(atendimento_id: UUID, status: str, posicao: int | None, total_aguardando: int, tempo_estimado_segundos: int | None)`
- `CancelarFilaRequest(motivo: str | None = None)`
- `CancelarFilaResponse(atendimento_id: UUID, status: str, cancelado_em: datetime, motivo: str | None)`
- `PioraClinicaRequest(atendimento_id: UUID, novos_sintomas: list[str], escala_dor: int = Field(ge=0, le=10, default=0), queixa_adicional: str = "")`
- `PioraClinicaResponse(atendimento_id: UUID, prioridade_clinica: int, alerta_samu_disparado: bool, redirecionado_emergencia: bool, nova_posicao: int | None, instrucoes: str | None)`

- [ ] **Passo 2: Criar dependências em `src/modules/queue/presentation/dependencies.py`**

Adicionar:
- `validar_medico_plantao`: valida que o usuário autenticado possui papel `MEDICO` (ou `ADMIN_GLOBAL`) pertencente ao tenant ativo.
- `validar_posse_atendimento`: valida que o paciente autenticado (via JWT ou intake token) é o titular do atendimento ou tem permissão administrativa.
- Exportar dependências anotadas: `MedicoPlantaoAuthDep`, `PosseAtendimentoAuthDep`.

- [ ] **Passo 3: Implementar `alocacao_router.py` seguindo a regra de routers finos**

Criar `src/modules/queue/presentation/routers/alocacao_router.py`:
- Router com prefixo `/fila` e tag `["Fila"]`.
- `POST /fila/chamar-proximo`:
  - Consome `tenant_id: TenantDep`, `medico: MedicoPlantaoAuthDep`, `service: FilaServiceDep`, `body: ChamarProximoRequest | None = None`.
  - Executa `adquirir_proximo_paciente`.
  - Retorna `ChamarProximoResponse`.
  - Zero imports de `sqlalchemy`, `infrastructure` ou `domain.models`.
  - Sem `HTTPException`.

- [ ] **Passo 4: Implementar `fila_router.py` seguindo a regra de routers finos**

Criar `src/modules/queue/presentation/routers/fila_router.py`:
- Router com prefixo `/fila` e tag `["Fila"]`.
- `GET /fila/posicao/{atendimento_id}`:
  - Consome `tenant_id: TenantDep`, `atendimento_id: UUID`, `_auth: PosseAtendimentoAuthDep`, `service: FilaServiceDep`.
  - Retorna `PosicaoFilaResponse`.
- `POST /fila/cancelar/{atendimento_id}`:
  - Consome `tenant_id: TenantDep`, `atendimento_id: UUID`, `body: CancelarFilaRequest | None`, `_auth: PosseAtendimentoAuthDep`, `service: FilaServiceDep`.
  - Retorna `CancelarFilaResponse`.
- `POST /fila/piora`:
  - Consome `tenant_id: TenantDep`, `body: PioraClinicaRequest`, `_auth: PosseAtendimentoAuthDep`, `service: FilaServiceDep`.
  - Retorna `PioraClinicaResponse`.
- Zero imports proibidos, sem `HTTPException`.

- [ ] **Passo 5: Conectar routers em `__init__.py` e `src/main.py`**

Em `src/modules/queue/presentation/routers/__init__.py`:
- Exportar `alocacao_router` e `fila_router`.
Em `src/main.py`:
- Incluir `api_v1.include_router(alocacao_router)` e `api_v1.include_router(fila_router)`.

- [ ] **Passo 6: Escrever testes unitários de integração HTTP dos routers**

Criar `tests/unit/test_alocacao_router.py` e `tests/unit/test_fila_router.py`:
- Testar chamadas autorizadas e não autorizadas (401/403).
- Testar retorno correto dos payloads e status codes (200 OK).
- Testar cenários de fila vazia e médico ocupado (409 Conflict).

- [ ] **Passo 7: Validar que os routers são finos com AST e modularidade com Tach**

Run: `uv run pytest tests/architecture/test_routers_are_thin.py`
Run: `uv run tach check`
Expected: 0 violações

- [ ] **Passo 8: Rodar testes unitários dos novos routers**

Run: `uv run pytest tests/unit/test_alocacao_router.py tests/unit/test_fila_router.py`
Expected: PASS

- [ ] **Passo 9: Commit**

```bash
git add src/modules/queue/presentation/ src/main.py tests/unit/test_alocacao_router.py tests/unit/test_fila_router.py
git commit -m "feat(queue): criar routers REST alocacao_router e fila_router em conformidade com ADR-001"
```

---

### Tarefa 6: Atualização da Documentação e Portão de Qualidade Final

**Files:**
- Modify: `docs/auditoria_completa_sistema.md`
- Modify: `docs/explanation/domains/queue-domain.md`
- Modify: `docs/explanation/domains/identity-domain.md`
- Modify: `docs/explanation/product-specification.md`

- [ ] **Passo 1: Atualizar `docs/auditoria_completa_sistema.md`**

- Marcar itens como saneados:
  - `NC-QUE-01 [SANEADO]`: Leitura e incremento da cota diária no Valkey integrado na admissão.
  - `NC-QUE-02 [SANEADO]`: Endpoints REST `POST /fila/chamar-proximo`, `GET /fila/posicao/{id}` e `POST /fila/cancelar/{id}` implementados.
  - `NC-MED-02 [SANEADO]`: Endpoint `POST /fila/piora` e salvaguarda de deterioração clínica RF-06 conectados.
  - `NC-REG-01 [SANEADO]`: Suporte a `nome_social` implementado no modelo `Paciente`, migration Alembic e schemas em conformidade com CFM 1.821/2007.
- Atualizar a tabela de Issues na Seção 8, marcando a Issue #53 como saneada/implementada.

- [ ] **Passo 2: Atualizar `docs/explanation/domains/queue-domain.md`**

- Adicionar documentação dos endpoints REST da fila:
  - `POST /api/v1/fila/chamar-proximo` (RF-03, double-lock Lua, 45s ring timeout).
  - `GET /api/v1/fila/posicao/{atendimento_id}` (estimativa de espera e tamanho da fila).
  - `POST /api/v1/fila/cancelar/{atendimento_id}` (desistência voluntária).
  - `POST /api/v1/fila/piora` (escape de emergência e reavaliação de score).
- Documentar a chave de contagem de admissões no Valkey (`queue:admissoes:{org_id}:{data}`) para RN05.
- Atentar para a regra do `scripts/docs_check.py`: blocos Python $\le 5$ linhas fora de `reference/`.

- [ ] **Passo 3: Atualizar `docs/explanation/domains/identity-domain.md`**

- Documentar o campo `nome_social` no modelo `Paciente` e seu preenchimento nas Fases 1 e 2 em conformidade com CFM 1.821/2007 e acolhimento do SUS.

- [ ] **Passo 4: Atualizar `docs/explanation/product-specification.md`**

- Na seção de RF-03 e RF-06, referenciar os endpoints REST implementados como a interface de apresentação oficial do sistema.

- [ ] **Passo 5: Executar validador de documentação**

Run: `uv run python scripts/docs_check.py`
Expected: Return code 0 (zero missing paths, zero python blocks > 5 lines)

- [ ] **Passo 6: Executar o portão de qualidade completo (`just check`)**

Run: `just check`
Expected:
- `just fmt`: formatado com ruff
- `just lint`: ruff check 0 erros
- `just typecheck`: basedpyright strict 0 erros
- `just tach`: tach check 0 erros
- `just test-unit`: 100% testes passando com cobertura
- `just test-integration`: 100% testes passando

- [ ] **Passo 7: Commit**

```bash
git add docs/
git commit -m "docs: atualizar auditoria, domains e especificacao com resolucao da Issue #53"
```

---

## Verificação e Critérios de Aceite

1. **Routers Finos (ADR-001)**:
   - `uv run pytest tests/architecture/test_routers_are_thin.py` passa com 0 violações.
   - Routers em `queue` não importam `sqlalchemy`, `infrastructure`, nem `domain.models`.
2. **Backpressure e Cota Diária (RN05)**:
   - Pacientes admitidos incrementam contador atômico no Valkey.
   - Quando `admissoes_hoje >= cota_diaria_maxima`, a admissão retorna `422/400/409` com código `COTA_ATINGIDA`.
3. **Endpoints REST da Fila**:
   - `POST /api/v1/fila/chamar-proximo` convoca paciente e bloqueia chamadas concorrentes com double-lock.
   - `GET /api/v1/fila/posicao/{id}` retorna posição e estimativa em segundos.
   - `POST /api/v1/fila/cancelar/{id}` transiciona para `CANCELADO_PACIENTE` e remove do ZSET.
   - `POST /api/v1/fila/piora` aciona escape SAMU para emergências ou recalcula score determinístico.
4. **Conformidade Regulatória Nome Social (CFM 1.821/2007)**:
   - Tabela `pacientes` possui coluna `nome_social`.
   - Migration Alembic `0005_paciente_nome_social.py` aplica e reverte sem erro.
   - Schemas de Fase 1 e 2 aceitam e retornam `nome_social`.
5. **Portão Oficial**:
   - `just check` executado com código de retorno 0.
