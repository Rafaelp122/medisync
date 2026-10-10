# Como Escrever Testes (Write Tests)

> Receitas práticas para escrever testes unitários e de integração seguindo o Padrão Ouro do MediSync.

---

## 1. Como Escrever um Teste Unitário (Camada U)

Testes unitários residem em `tests/unit/`, rodam 100% em memória, não usam Docker e devem executar em milissegundos.

### Exemplo: Testando Regras de Domínio ou Modelos Ricos
Para validar entidades e cálculos de domínio, utilize as fábricas em memória de `tests/factories/`:

```python
from tests.factories.identity import make_organizacao, make_profissional
from tests.factories.queue import make_atendimento
from src.modules.queue.domain.models import StatusAtendimento

def test_medico_pode_atender_quando_ativo() -> None:
    # Arrange
    org = make_organizacao()
    medico = make_profissional(organizacao_id=org.id, papel="MEDICO", ativo=True)
    atendimento = make_atendimento(organizacao_id=org.id, status=StatusAtendimento.APTO_PARA_CHAMADA)

    # Act & Assert
    assert medico.is_medico() is True
    assert atendimento.pode_ser_alocado() is True
```

### Exemplo: Testando Services com Mocks de Sessão
Para testar métodos de aplicação/serviço que recebem uma `AsyncSession`, utilize a fixture compartilhada `mock_db_session` ou dublês de `tests/doubles.py`:

```python
import pytest
from unittest.mock import AsyncMock
from tests.helpers import make_pep_service
from src.modules.consultation.domain.exceptions import ConsultaFinalizadaError

async def test_pep_service_rejeita_edicao_em_consulta_finalizada(mock_db_session: AsyncMock) -> None:
    # Arrange
    service = make_pep_service(mock_db_session)
    
    # Act & Assert
    with pytest.raises(ConsultaFinalizadaError):
        await service.validar_alteracao_permitida(consulta_finalizada=True)
```

---

## 2. Como Escrever um Teste de Integração (Camada I)

Testes de integração residem em `tests/integration/` e utilizam o banco de dados e Valkey reais.

### Exemplo: Testando um Endpoint HTTP Autenticado
Utilize as fixtures globais `async_client`, `authed_client_factory` e a fábrica de cenários `seed_clinical_scenario`:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories.scenarios import seed_clinical_scenario
from src.core.auth.roles import Role

@pytest.mark.asyncio
async def test_medico_consegue_registrar_evolucao_soap(
    db_session: AsyncSession,
    authed_client_factory: Any,
) -> None:
    # 1. Arrange: Popula o banco com 1 única linha canônica (Org, Paciente, Médico, Atendimento)
    cenario = await seed_clinical_scenario(db_session)

    # 2. Cliente HTTP pré-autenticado com token JWT real e X-Tenant-ID
    client: AsyncClient = authed_client_factory(
        papel=Role.MEDICO,
        org_id=cenario.organizacao.id,
        usuario_id=cenario.medico.id,
    )

    payload = {
        "anamnese": "Paciente com dor de cabeça e febre moderada.",
        "conduta": "Prescrito repouso e hidratação.",
        "cid10_principal": "R51",
    }

    # 3. Act
    response = await client.post(
        f"/api/v1/consultas/{cenario.atendimento.id}/evolucao",
        json=payload,
    )

    # 4. Assert
    assert response.status_code == 201
    data = response.json()
    assert data["atendimento_id"] == str(cenario.atendimento.id)
```

---

## 3. Como Limpar Estado em Testes de Integração

* **Automático:** A fixture global `clean_db_and_valkey` (ou `clean_db`) em `tests/conftest.py` é executada automaticamente antes e depois de cada teste de integração.
* **Sob demanda:** Caso seu teste realize operações concorrentes que exijam limpeza intermediária:
  ```python
  from tests.helpers import clean_database_tables, clean_valkey_keys

  # Limpar tabelas mantendo o schema e RLS
  await clean_database_tables()

  # Limpar chaves voláteis do Valkey
  await clean_valkey_keys("fila:*", "lock:*")
  ```

---

## 4. O que NUNCA fazer em testes

1. **Nunca use `DROP SCHEMA public CASCADE;`:** Isso destrói a infraestrutura de outros testes concorrentes e remove grants da role `medisync_app`.
2. **Nunca use `Base.metadata.create_all` em testes:** O schema deve ser provisionado canonicamente via migrações do Alembic (`just migrate`).
3. **Nunca copie blocos de 30 linhas de `session.add(...)`:** Use `seed_clinical_scenario(session)` ou as fábricas de persistência de `tests/factories/scenarios.py`.
4. **Nunca instancie `ASGITransport(app=app)` manualmente:** Use a fixture `async_client` ou `authed_client_factory` de `tests/conftest.py`.
5. **Nunca deixe testes sem tipagem estrita:** O `just typecheck` (`basedpyright`) roda em modo estrito tanto para `src/` quanto para `tests/`.
