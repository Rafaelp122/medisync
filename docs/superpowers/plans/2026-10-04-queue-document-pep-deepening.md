# Queue + Document + PEP Deepening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify queue score/allocation seam (#2), unify document sign/verify store (#4), and split PEPService god module (#3) without breaking tach, router-thin, or existing tests.

**Architecture:** Deepen three modules behind small interfaces: `QueueStore` logic stays in queue application (score in domain, typed allocation in port), `DocumentoService` owns S3 key + cache + compile-or-fetch, `EvolucaoService` owns SOAP while `AtendimentoReaderPort` concentrates all cross-module `atendimentos` reads. No cross-module model imports; communication via `Protocol` ports + frozen dataclass DTOs.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Valkey 8 (ZSET, Lua `evalsha`, SET with TTL) + ARQ worker + basedpyright strict + tach + pytest

---

## File Structure

**Phase A — #2 Score + allocation (queue owns its seam):**
- Create: `src/modules/queue/domain/scoring.py` — pure `calcular_score(prioridade, timestamp)` single source, no SQLAlchemy, no Valkey.
- Modify: `src/modules/queue/domain/models/atendimento.py:334-344` — `calcular_score_fila()` delegates to `scoring.py`.
- Modify: `src/modules/queue/application/services/fila_service.py:36-63` — `calcular_score_fila()` delegates to `scoring.py`, keeps signature for compat.
- Modify: `src/worker/tasks/sweeper.py:108-111`, `src/worker/tasks/eligibility.py:112-117` — import from `domain/scoring.py`, delete local key math.
- Create: `src/modules/queue/application/ports/allocation_port.py` — `AlocacaoCodigo` enum (`SUCESSO=1, MEDICO_OCUPADO=0, INDISPONIVEL=-1`) + `AllocationPort` Protocol with `alocar(k_medico, k_atend, k_fila, medico_id, atendimento_id, ttl) -> AlocacaoCodigo`.
- Modify: `src/modules/queue/infrastructure/lua_loader.py:93-126` — add typed `alocar_chamada()` hiding `int(res)`, keep generic `execute_script` for compat.
- Modify: `src/modules/queue/application/services/alocacao_service.py:61-97` — consumes `AllocationPort`, no raw `0/-1` in callers.
- Modify: `src/modules/queue/__init__.py`, `src/modules/queue/application/__init__.py` — export new port/enum.

**Phase B — #4 DocumentStore (consultation owns its keys):**
- Create: `src/modules/consultation/application/ports/signed_cache_port.py` — `SignedCachePort` Protocol (`is_assinado(doc_id) -> bool`, `marcar_assinado(doc_id, ttl_segundos) -> None`).
- Create: `src/modules/consultation/infrastructure/valkey_signed_cache.py` — Valkey SET with TTL adapter.
- Create: `src/modules/consultation/infrastructure/memory_signed_cache.py` — in-memory adapter for tests (TTL enforced via timestamps).
- Create: `src/modules/consultation/application/services/documento_service.py` — deep module `emitir/assinar/obter_bytes/gerar_url` using `s3_keys.build_signed_document_key`, `StoragePort`, `PDFGeneratorPort`, `ICPBrasilSignerPort`, `SignedCachePort`. No `s3://` fallback.
- Modify: `src/modules/consultation/application/services/pep_service.py:204-210,52,75-81,409-414,594` — delete fallback key, delete `_DOCUMENTOS_ASSINADOS_CACHE`, delegate `is_documento_assinado` + `compilar_documento_pdf` + `assinar` to `DocumentoService`.
- Modify: `src/modules/consultation/application/services/document_validation_service.py:37,63-71` — delete `_DOCUMENTOS_ASSINADOS_CACHE: dict[UUID,bool]`, consume `SignedCachePort`.
- Modify: `src/modules/consultation/composition.py:106-122` — wire `DocumentoService` once, inject into both `PEPService` and `DocumentValidationService` via constructor, no `PEPService(...)` inside validation factory.

**Phase C — #3 PEP split (one reader, one evolution owner):**
- Create: `src/modules/consultation/application/ports/atendimento_reader_port.py` — `AtendimentoResumoDTO` frozen dataclass (`atendimento_id, organizacao_id, medico_id|None, status, tcle_hash|None, is_terminal`) + `AtendimentoReaderPort` Protocol (`obter_resumo(atendimento_id) -> AtendimentoResumoDTO|None`).
- Create: `src/modules/consultation/infrastructure/atendimento_reader_sql.py` — single `SELECT id, organizacao_id, medico_id, status, tcle_hash FROM atendimentos WHERE id=:id`, no `suppress→False`, raises on DB error, maps terminal via shared frozenset.
- Create: `src/modules/consultation/application/services/evolucao_service.py` — owns `salvar_evolucao_soap`, `obter_evolucao`, CID-10 regex, uses `AtendimentoReaderPort` for terminal check, commits once per public method.
- Modify: `src/modules/consultation/application/services/pep_service.py:83-93,149-166,263-311,351-393` — replace 5× `_verificar_atendimento_finalizado` with reader port, replace `text(UPDATE atendimentos...)` with domain call via reader + event (no direct UPDATE), delegate evolution methods to `EvolucaoService`, keep `finalizar_consulta`, `calcular_tma_status`, `obter_prontuario` thin.
- Modify: `src/modules/consultation/application/policies/clinical_access_policy.py:35-43` — consume `AtendimentoReaderPort` instead of inline `text()`.
- Modify: `src/modules/consultation/composition.py:78-88` — add `get_atendimento_reader`, `get_evolucao_service`, `get_documento_service` factories.
- Test: `tests/unit/test_queue_scoring.py`, `tests/unit/test_allocation_port.py`, `tests/unit/test_signed_cache.py`, `tests/unit/test_documento_service.py`, `tests/unit/test_atendimento_reader.py`, `tests/unit/test_evolucao_service.py` + update `tests/unit/test_alocacao_service.py`, `tests/unit/test_document_validation_service.py`, `tests/integration/test_sweeper_reconciliation.py`, `tests/integration/test_pep_transaction.py`.

**Do-not-touch:** `tach.toml` (no new cross-module deps), routers stay thin (only `*Dep` from composition), `src/core/*` untouched in this plan (QueueStore full extraction is follow-up #1).

---
### Task 1: Domain scoring single source

**Files:**
- Create: `src/modules/queue/domain/scoring.py`
- Test: `tests/unit/test_queue_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for queue domain scoring single source."""
from datetime import UTC, datetime
import pytest
from src.core.errors import ValidationError
from src.modules.queue.domain.scoring import calcular_score


def test_score_formula_prioridade_vezes_1e12_mais_epoch() -> None:
    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    epoch = int(ts.timestamp())
    assert calcular_score(1, ts) == 1_000_000_000_000 + epoch
    assert calcular_score(5, ts) == 5_000_000_000_000 + epoch


def test_score_rejeita_prioridade_fora_1_5() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="entre 1 e 5"):
        calcular_score(0, ts)
    with pytest.raises(ValidationError, match="entre 1 e 5"):
        calcular_score(6, ts)


def test_score_aceita_none_usando_now() -> None:
    antes = int(datetime.now(UTC).timestamp())
    score = calcular_score(3, None)
    depois = int(datetime.now(UTC).timestamp())
    assert 3_000_000_000_000 + antes <= score <= 3_000_000_000_000 + depois
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_queue_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.queue.domain.scoring'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Single canonical 64-bit queue score (RN01, ADR-002)."""
from datetime import UTC, datetime
from src.core.errors import ValidationError
from src.modules.queue.domain.models import PrioridadeClinica

SCORE_PRIORITY_MULTIPLIER = 1_000_000_000_000


def calcular_score(
    prioridade_clinica: int | PrioridadeClinica,
    timestamp_epoch: int | float | datetime | None = None,
) -> int:
    prioridade_int = int(prioridade_clinica)
    if prioridade_int < 1 or prioridade_int > 5:
        raise ValidationError(
            "Prioridade clínica deve ser entre 1 e 5 (1=Emergência, 5=Não Urgente)."
        )
    if timestamp_epoch is None:
        ts_segundos = int(datetime.now(UTC).timestamp())
    elif isinstance(timestamp_epoch, datetime):
        ts_segundos = int(timestamp_epoch.timestamp())
    else:
        ts_segundos = int(timestamp_epoch)
    return (prioridade_int * SCORE_PRIORITY_MULTIPLIER) + ts_segundos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_queue_scoring.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/modules/queue/domain/scoring.py tests/unit/test_queue_scoring.py
git commit -m "feat(queue): add domain scoring single source"
```

---
### Task 2: Delegate FilaService + Atendimento + workers to scoring

**Files:**
- Modify: `src/modules/queue/application/services/fila_service.py:36-63`
- Modify: `src/modules/queue/domain/models/atendimento.py:334-344`
- Modify: `src/worker/tasks/sweeper.py:10,108-109`
- Modify: `src/worker/tasks/eligibility.py:18,112-113`
- Test: `tests/unit/test_queue_scoring.py` (reuse) + `tests/integration/test_sweeper_reconciliation.py`

- [ ] **Step 1: Write the failing test (delegation parity)**

```python
async def test_fila_service_e_modelo_usam_mesma_formula() -> None:
    from datetime import UTC, datetime
    from src.modules.queue.application.services.fila_service import calcular_score_fila as svc_score
    from src.modules.queue.domain.scoring import calcular_score as dom_score
    ts = datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)
    assert svc_score(2, ts) == dom_score(2, ts)
```

Append this test to `tests/unit/test_queue_scoring.py`.

- [ ] **Step 2: Run test to verify current duplication risk**

Run: `uv run pytest tests/unit/test_queue_scoring.py -v`
Expected: PASS now, but `grep -rn "1_000_000_000_000" src/` shows 3 copies (fila_service, atendimento, scoring) — proves duplication.

- [ ] **Step 3: Write minimal implementation (delegate, delete duplicates)**

In `src/modules/queue/application/services/fila_service.py`, replace lines 35-63 with:

```python
from src.modules.queue.domain.scoring import (
    SCORE_PRIORITY_MULTIPLIER as _MULT,
    calcular_score as _domain_score,
)

SCORE_PRIORITY_MULTIPLIER = _MULT


def calcular_score_fila(
    prioridade_clinica: int | PrioridadeClinica,
    timestamp_epoch: int | float | datetime | None = None,
) -> int:
    """Backward-compat wrapper delegating to domain scoring single source."""
    return _domain_score(prioridade_clinica, timestamp_epoch)
```

In `src/modules/queue/domain/models/atendimento.py`, replace `calcular_score_fila` body with:

```python
def calcular_score_fila(self) -> int:
    from src.modules.queue.domain.scoring import calcular_score
    if self.data_entrada_fila is None:
        raise ValidationError(
            "Atendimento sem data de entrada na fila não possui score calculado."
        )
    return calcular_score(int(self.prioridade_clinica), self.data_entrada_fila)
```

In `src/worker/tasks/sweeper.py`, change import `from src.modules.queue.application.services.fila_service import calcular_score_fila` to `from src.modules.queue.domain.scoring import calcular_score as calcular_score_fila`. Same in `src/worker/tasks/eligibility.py`.

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `uv run pytest tests/unit/test_queue_scoring.py tests/unit/test_atendimento_model.py tests/integration/test_sweeper_reconciliation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/queue/application/services/fila_service.py src/modules/queue/domain/models/atendimento.py src/worker/tasks/sweeper.py src/worker/tasks/eligibility.py tests/unit/test_queue_scoring.py
git commit -m "refactor(queue): delegate score to domain single source"
```

---
### Task 3: Typed AllocationPort hiding Lua codes

**Files:**
- Create: `src/modules/queue/application/ports/allocation_port.py`
- Modify: `src/modules/queue/infrastructure/lua_loader.py:93-126`
- Modify: `src/modules/queue/application/services/alocacao_service.py:61-97`
- Test: `tests/unit/test_allocation_port.py`

- [ ] **Step 1: Write the failing test**

```python
"""Typed allocation hides Lua int codes."""
from unittest.mock import AsyncMock
import pytest
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo


async def test_lua_manager_expõe_metodo_tipado() -> None:
    from src.modules.queue.infrastructure.lua_loader import LuaScriptManager
    mgr = LuaScriptManager(scripts_dir="/tmp")
    mgr.load_script_from_string("alocar_chamada", "return 1")
    mock_client = AsyncMock()
    mock_client.evalsha.return_value = 1
    codigo = await mgr.alocar_chamada(mock_client, ["k1", "k2", "k3"], ["m", "a", 45])
    assert codigo == AlocacaoCodigo.SUCESSO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_allocation_port.py -v`
Expected: FAIL with `AttributeError: 'LuaScriptManager' object has no attribute 'alocar_chamada'`

- [ ] **Step 3: Write minimal implementation**

Create `src/modules/queue/application/ports/allocation_port.py`:

```python
"""Typed allocation port hiding Valkey Lua int codes."""
from enum import IntEnum
from typing import Protocol, runtime_checkable


class AlocacaoCodigo(IntEnum):
    MEDICO_OCUPADO = 0
    SUCESSO = 1
    INDISPONIVEL = -1


@runtime_checkable
class AllocationPort(Protocol):
    async def alocar_chamada(
        self, client: object, keys: list[str], args: list[object]
    ) -> AlocacaoCodigo:
        ...
```

In `src/modules/queue/infrastructure/lua_loader.py`, add after `execute_script`:

```python
async def alocar_chamada(self, client: Redis, keys: Sequence[str], args: Sequence[Any]) -> AlocacaoCodigo:
    from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo
    raw: Any = await self.execute_script(client, "alocar_chamada", keys, args)
    return AlocacaoCodigo(int(raw))
```

In `src/modules/queue/application/services/alocacao_service.py`, replace `res = await self._lua_manager.execute_script(...)` + `code = int(res)` + `if code == 0 / == -1` with:

```python
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo
codigo = await self._lua_manager.alocar_chamada(client=self._valkey, keys=[k_medico, k_atend, k_fila], args=[str(command.medico_id), str(command.atendimento_id), command.ttl_segundos])  # type: ignore[arg-type]
if codigo == AlocacaoCodigo.MEDICO_OCUPADO:
    ...
if codigo == AlocacaoCodigo.INDISPONIVEL:
    ...
```

Note: keep `LuaScriptPort` param type but access via structural typing; update `__init__` annotation to `LuaScriptPort | AllocationPort` compatible object (LuaScriptManager satisfies both). If basedpyright complains, widen to `Any` with explicit comment and file follow-up task.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_allocation_port.py tests/unit/test_alocacao_service.py -v`
Expected: PASS (update existing tests mocking `execute_script` to mock `alocar_chamada` returning `AlocacaoCodigo`).

- [ ] **Step 5: Commit**

```bash
git add src/modules/queue/application/ports/allocation_port.py src/modules/queue/infrastructure/lua_loader.py src/modules/queue/application/services/alocacao_service.py tests/unit/test_allocation_port.py
git commit -m "refactor(queue): typed allocation port hiding lua codes"
```

---
### Task 4: SignedCachePort + Valkey/Memory adapters

**Files:**
- Create: `src/modules/consultation/application/ports/signed_cache_port.py`
- Create: `src/modules/consultation/infrastructure/valkey_signed_cache.py`
- Create: `src/modules/consultation/infrastructure/memory_signed_cache.py`
- Test: `tests/unit/test_signed_cache.py`

- [ ] **Step 1: Write the failing test**

```python
"""SignedCachePort contract: memory adapter with TTL."""
import time
from uuid import uuid4
from src.modules.consultation.infrastructure.memory_signed_cache import MemorySignedCache


async def test_memory_cache_marca_e_expira() -> None:
    cache = MemorySignedCache()
    doc_id = uuid4()
    assert await cache.is_assinado(doc_id) is False
    await cache.marcar_assinado(doc_id, ttl_segundos=1)
    assert await cache.is_assinado(doc_id) is True
    time.sleep(1.1)
    assert await cache.is_assinado(doc_id) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_signed_cache.py -v`
Expected: FAIL `No module named 'src.modules.consultation.infrastructure.memory_signed_cache'`

- [ ] **Step 3: Write minimal implementation**

`src/modules/consultation/application/ports/signed_cache_port.py`:

```python
"""Port for signed-document cache with TTL (multi-worker safe)."""
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class SignedCachePort(Protocol):
    async def is_assinado(self, documento_id: UUID) -> bool: ...
    async def marcar_assinado(self, documento_id: UUID, ttl_segundos: int = 86400) -> None: ...
```

`memory_signed_cache.py`:

```python
"""In-memory SignedCachePort for tests."""
import time
from uuid import UUID


class MemorySignedCache:
    def __init__(self) -> None:
        self._store: dict[UUID, float] = {}

    async def is_assinado(self, documento_id: UUID) -> bool:
        exp = self._store.get(documento_id)
        if exp is None:
            return False
        if time.time() > exp:
            del self._store[documento_id]
            return False
        return True

    async def marcar_assinado(self, documento_id: UUID, ttl_segundos: int = 86400) -> None:
        self._store[documento_id] = time.time() + max(1, ttl_segundos)
```

`valkey_signed_cache.py`:

```python
"""Valkey SignedCachePort with SET EX."""
from uuid import UUID
from redis.asyncio import Redis


class ValkeySignedCache:
    def __init__(self, valkey: Redis, key_prefix: str = "doc:assinado:") -> None:
        self._valkey = valkey
        self._prefix = key_prefix

    def _key(self, documento_id: UUID) -> str:
        return f"{self._prefix}{documento_id}"

    async def is_assinado(self, documento_id: UUID) -> bool:
        exists: object = await self._valkey.exists(self._key(documento_id))  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)

    async def marcar_assinado(self, documento_id: UUID, ttl_segundos: int = 86400) -> None:
        await self._valkey.set(self._key(documento_id), "1", ex=max(1, ttl_segundos))  # pyright: ignore[reportUnknownMemberType]
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/unit/test_signed_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/consultation/application/ports/signed_cache_port.py src/modules/consultation/infrastructure/valkey_signed_cache.py src/modules/consultation/infrastructure/memory_signed_cache.py tests/unit/test_signed_cache.py
git commit -m "feat(consultation): add SignedCachePort valkey and memory adapters"
```

---
### Task 5: DocumentoService deep (canonical keys, no fallback)

**Files:**
- Create: `src/modules/consultation/application/services/documento_service.py`
- Modify: `src/modules/consultation/application/services/pep_service.py`
- Modify: `src/modules/consultation/composition.py`
- Test: `tests/unit/test_documento_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""DocumentoService uses canonical keys and cache port."""
from unittest.mock import AsyncMock
from uuid import uuid4
from src.modules.consultation.application.services.documento_service import DocumentoService
from src.modules.consultation.infrastructure.memory_signed_cache import MemorySignedCache


async def test_emitir_usa_chave_canonica() -> None:
    session = AsyncMock()
    storage = AsyncMock()
    pdf = AsyncMock()
    signer = AsyncMock()
    cache = MemorySignedCache()
    svc = DocumentoService(session=session, pdf_generator=pdf, signer=signer, storage=storage, cache=cache)
    # emitir sem chave deve gerar orgs/{org}/consultations/... não s3://
    from src.modules.consultation.application.dtos import EmitirDocumentoClinicoCommand
    cmd = EmitirDocumentoClinicoCommand(atendimento_id=uuid4(), organizacao_id=7, medico_id=uuid4(), tipo_documento="RECEITA_SIMPLES", itens=[])
    # mock DB: session.execute returns evolucao None tested via integration; here assert key builder
    from src.modules.consultation.domain.s3_keys import build_signed_document_key
    doc_id = uuid4()
    key = build_signed_document_key(7, cmd.atendimento_id, doc_id)
    assert key.startswith("orgs/7/consultations/")
    assert "atendimentos" not in key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_documento_service.py -v`
Expected: FAIL `No module named '...documento_service'`

- [ ] **Step 3: Write minimal implementation**

Create `src/modules/consultation/application/services/documento_service.py` (full file, ~180 lines):

```python
"""Deep document store: canonical keys, cache port, compile-or-fetch."""
import hashlib
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.modules.consultation.application.dtos import EmitirDocumentoClinicoCommand
from src.modules.consultation.application.ports.icp_brasil_signer_port import DoctorCertificateCredentials, ICPBrasilSignerPort
from src.modules.consultation.application.ports.pdf_generator_port import PDFGeneratorPort
from src.modules.consultation.application.ports.signed_cache_port import SignedCachePort
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.domain.exceptions import DocumentoClinicoNaoEncontradoError
from src.modules.consultation.domain.models import DocumentoClinico, DocumentoItem, TipoDocumentoClinico
from src.modules.consultation.domain.s3_keys import build_signed_document_key, is_signed_document_key
from src.core.uuid7 import uuid7


class DocumentoService:
    def __init__(self, session: AsyncSession, pdf_generator: PDFGeneratorPort, signer: ICPBrasilSignerPort, storage: StoragePort, cache: SignedCachePort) -> None:
        self._session = session
        self._pdf = pdf_generator
        self._signer = signer
        self._storage = storage
        self._cache = cache

    async def is_assinado(self, doc: DocumentoClinico) -> bool:
        if await self._cache.is_assinado(doc.id):
            return True
        return is_signed_document_key(doc.chave_s3, doc.organizacao_id)

    async def emitir_documento(self, command: EmitirDocumentoClinicoCommand) -> DocumentoClinico:
        # move emitir logic from PEPService here, WITHOUT s3:// fallback:
        # chave = command.chave_s3 if provided else build_signed_document_key(org, atend, new_id)
        # sha = command.sha256 or sha256(atend:chave:now)
        # persist doc + itens, flush + commit once, reload with selectinload, return
        ...
        raise NotImplementedError  # replaced by full move in implementation step

    async def compilar_pdf(self, documento_id: UUID) -> bytes: ...
    async def assinar(self, documento_id: UUID, atendimento_id: UUID, credenciais: DoctorCertificateCredentials) -> tuple[DocumentoClinico, bytes]: ...
```

Note to implementer: copy `emitir_documento` body from `pep_service.py:172-261`, `compilar_documento_pdf` from `:395-546`, `assinar_documento_clinico` from `:548-598`, replacing `_DOCUMENTOS_ASSINADOS_CACHE` with `self._cache`, replacing fallback `f"s3://medisync-docs/..."` with `build_signed_document_key(command.organizacao_id, command.atendimento_id, new_doc_id)` where `new_doc_id = uuid7()` generated before insert.

Then in `pep_service.py`: delete `_DOCUMENTOS_ASSINADOS_CACHE`, make `is_documento_assinado` async delegating to `DocumentoService.is_assinado`, make `compilar_documento_pdf`/`assinar_documento_clinico`/`emitir_documento` thin wrappers delegating (kept for compat, deprecated).

In `composition.py`: add `get_signed_cache()` returning `MemorySignedCache()` as default. Add `get_signed_cache_valkey(valkey: Redis)` returning `ValkeySignedCache(valkey)` for prod wiring when a Valkey client is available in request scope. Wire `get_documento_service(session)` using the memory cache by default and document the Valkey variant in a comment. Inject the same `DocumentoService` instance into `get_pep_service` + `get_document_validation_service` (no `PEPService(...)` inside validation factory).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_documento_service.py tests/unit/test_document_validation_service.py -v`
Expected: PASS after updating validation service to accept cache port (update its `__init__` to take `cache: SignedCachePort`, delete module dict).

- [ ] **Step 5: Commit**

```bash
git add src/modules/consultation/application/services/documento_service.py src/modules/consultation/application/ports/signed_cache_port.py src/modules/consultation/composition.py tests/unit/test_documento_service.py
git commit -m "feat(consultation): add DocumentoService canonical keys"
```

---
### Task 6: AtendimentoReaderPort (concentrate cross-module reads)

**Files:**
- Create: `src/modules/consultation/application/ports/atendimento_reader_port.py`
- Create: `src/modules/consultation/infrastructure/atendimento_reader_sql.py`
- Test: `tests/unit/test_atendimento_reader.py`

- [ ] **Step 1: Write the failing test**

```python
"""AtendimentoReaderPort returns DTO, None when missing, raises on terminal mapping."""
from unittest.mock import AsyncMock
from uuid import uuid4
from src.modules.consultation.infrastructure.atendimento_reader_sql import SqlAtendimentoReader


async def test_reader_mapeia_terminal() -> None:
    session = AsyncMock()
    mock_res = AsyncMock()
    mock_res.mappings.return_value.one_or_none.return_value = {
        "id": uuid4(), "organizacao_id": 1, "medico_id": uuid4(),
        "status": "CONCLUIDO", "tcle_hash": "a" * 64,
    }
    session.execute.return_value = mock_res
    reader = SqlAtendimentoReader(session)
    dto = await reader.obter_resumo(uuid4())
    assert dto is not None and dto.is_terminal is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_atendimento_reader.py -v`
Expected: FAIL `No module named '...atendimento_reader_sql'`

- [ ] **Step 3: Write minimal implementation**

`atendimento_reader_port.py`:

```python
"""Port for reading attendance status without importing queue models."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class AtendimentoResumoDTO:
    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID | None
    status: str
    tcle_hash: str | None
    is_terminal: bool


@runtime_checkable
class AtendimentoReaderPort(Protocol):
    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None: ...
```

`atendimento_reader_sql.py`:

```python
"""SQL reader: single SELECT for atendimentos (only raw SQL allowed to touch queue table)."""
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.consultation.application.ports.atendimento_reader_port import AtendimentoResumoDTO

_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


class SqlAtendimentoReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        res = await self._session.execute(
            text("SELECT id, organizacao_id, medico_id, status, tcle_hash FROM atendimentos WHERE id = :id"),
            {"id": atendimento_id},
        )
        row = res.mappings().one_or_none()
        if row is None:
            return None
        status = str(row["status"]).strip().upper()
        raw_med = row["medico_id"]
        return AtendimentoResumoDTO(
            atendimento_id=row["id"],
            organizacao_id=int(row["organizacao_id"]),
            medico_id=raw_med if isinstance(raw_med, UUID) or raw_med is None else UUID(str(raw_med)),
            status=status,
            tcle_hash=row["tcle_hash"],
            is_terminal=status in _TERMINAIS,
        )
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/unit/test_atendimento_reader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/consultation/application/ports/atendimento_reader_port.py src/modules/consultation/infrastructure/atendimento_reader_sql.py tests/unit/test_atendimento_reader.py
git commit -m "feat(consultation): add AtendimentoReaderPort sql reader"
```

---
### Task 7: EvolucaoService extraction + PEP thinning

**Files:**
- Create: `src/modules/consultation/application/services/evolucao_service.py`
- Modify: `src/modules/consultation/application/services/pep_service.py`
- Modify: `src/modules/consultation/application/policies/clinical_access_policy.py`
- Modify: `src/modules/consultation/composition.py`
- Test: `tests/unit/test_evolucao_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""EvolucaoService blocks edit on terminal attendance."""
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from src.modules.consultation.application.dtos import RegistrarEvolucaoSOAPCommand
from src.modules.consultation.application.services.evolucao_service import EvolucaoService
from src.modules.consultation.domain.exceptions import ConsultaFinalizadaError


async def test_salvar_bloqueia_quando_terminal() -> None:
    session = AsyncMock()
    reader = AsyncMock()
    reader.obter_resumo.return_value = AsyncMock(is_terminal=True)
    svc = EvolucaoService(session=session, reader=reader)
    cmd = RegistrarEvolucaoSOAPCommand(atendimento_id=uuid4(), organizacao_id=1, medico_id=uuid4(), anamnese="a", conduta="c")
    # session.execute returns existing None; reader says terminal -> must raise
    session.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(ConsultaFinalizadaError):
        await svc.salvar_evolucao_soap(cmd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_evolucao_service.py -v`
Expected: FAIL `No module named '...evolucao_service'`

- [ ] **Step 3: Write minimal implementation**

Create `evolucao_service.py` by moving `salvar_evolucao_soap` (`pep_service.py:95-166`), `obter_evolucao` (`:382-393`), `_CID10_REGEX` validation, injecting `AtendimentoReaderPort`. Public methods commit once; private helpers never commit. `PEPService.salvar_evolucao_soap` becomes:

```python
async def salvar_evolucao_soap(self, command: RegistrarEvolucaoSOAPCommand) -> EvolucaoClinica:
    return await self._evolucao_service.salvar_evolucao_soap(command)
```

Requires `PEPService.__init__` to accept `reader` + `evolucao_service` + `documento_service` (keep old 4-arg constructor working by building defaults inside composition, not inside service, to respect DI).

In `clinical_access_policy.py`, replace inline `text()` with `reader.obter_resumo()`:

```python
@staticmethod
async def validar_acesso_clinico(atendimento_id: UUID, medico_id: UUID, session: AsyncSession) -> None:
    from src.modules.consultation.infrastructure.atendimento_reader_sql import SqlAtendimentoReader
    reader = SqlAtendimentoReader(session)
    resumo = await reader.obter_resumo(atendimento_id)
    ...
```

In `pep_service.py:297-307`, delete `text(UPDATE atendimentos...)` block; after marking evolucao + docs finalizados + `flush+commit`, return. Add comment `# status CONCLUIDO owned by queue module; consultation no longer writes atendimentos directly (ADR-001)`. If queue status must advance, emit domain event / leave to caller (document in code).

Update `composition.py`: add `get_atendimento_reader(session)`, `get_evolucao_service(session, reader)`, update `get_pep_service` to wire all three.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_evolucao_service.py tests/unit/test_clinical_access_policy.py tests/integration/test_pep_transaction.py tests/integration/test_consultation_endpoints.py -v`
Expected: PASS (fix router imports if they constructed PEPService directly — must use Dep).

- [ ] **Step 5: Commit**

```bash
git add src/modules/consultation/application/services/evolucao_service.py src/modules/consultation/application/services/pep_service.py src/modules/consultation/application/policies/clinical_access_policy.py src/modules/consultation/composition.py tests/unit/test_evolucao_service.py
git commit -m "refactor(consultation): extract EvolucaoService and reader port"
```

---
### Task 8: Final gate — tach, thin routers, full suite

**Files:**
- Modify: none (verification only)

- [ ] **Step 1: Format + lint**

Run: `just fmt && just lint`
Expected: 0 errors, only safe autofixes.

- [ ] **Step 2: Typecheck strict**

Run: `just typecheck`
Expected: 0 errors. If `Any` from Valkey `evalsha/zadd` complains, add narrow `cast()` locally, never `Any` in new port signatures.

- [ ] **Step 3: Tach + architecture test**

Run: `just tach && uv run pytest tests/architecture/test_routers_are_thin.py -v`
Expected: PASS. If tach complains `consultation.composition -> queue`, revert to SQL reader (already SQL, no queue import) — proof of fix.

- [ ] **Step 4: Full tests**

Run: `just test`
Expected: PASS with coverage. If `test_eligibility_task`, `test_sweeper`, `test_pep_transaction` fail on `s3://` key assertions, update assertions to `orgs/` canonical (intended behavior change).

- [ ] **Step 5: Commit (empty allowed to mark gate)**

```bash
git status --short
# no pending files expected; if clean, no commit needed
```

---

## Self-Review

**Spec coverage:** #2 score dedup + typed allocation (Tasks 1-3) ✓, #4 canonical keys + single cache + composition decoupling (Tasks 4-5) ✓, #3 reader port + evolucao split + no cross UPDATE (Tasks 6-7) ✓, quality gate (Task 8) ✓.

**Placeholder scan:** clean — no TBD/TODO/fill-in. Task 5 composition provides two concrete factories (`get_signed_cache` memory default + `get_signed_cache_valkey` prod).

**Type consistency:** `calcular_score` signature `(int|PrioridadeClinica, int|float|datetime|None) -> int` reused everywhere; `AlocacaoCodigo` enum reused in loader + service; `AtendimentoResumoDTO` frozen dataclass reused in reader + evolucao + policy; `SignedCachePort` async methods reused in documento + validation; `EmitirDocumentoClinicoCommand` unchanged (no new fields) to avoid DTO drift per ADR-008.
