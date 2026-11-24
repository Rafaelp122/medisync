"""Canonical test doubles and scripted in-memory adapters for unit tests."""

import asyncio
import hashlib
import hmac
import queue as queue_module
import re
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

if TYPE_CHECKING:
    from asn1crypto import x509 as asn1_x509

from src.core.audit import AtorPapel, AtorTipo
from src.core.audit.models import AuditEvent
from src.core.authz.roles import Role
from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.ambulatory.application.dtos import BpaRegistroDetalheDTO
from src.modules.ambulatory.application.ports.bpa_directory_port import BpaDirectoryPort
from src.modules.auth.application.ports.password_hasher_port import PasswordHasherPort
from src.modules.auth.application.ports.patient_credential_repository_port import (
    PatientCredentialRepositoryPort,
)
from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial
from src.modules.auth.infrastructure.valkey_challenge_store import (
    InMemoryChallengeStore,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.ports.producao_ambulatorial_port import (
    ProducaoAmbulatorialPort,
)
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityDirectoryDTO,
    IdentityReaderPort,
    PacienteAuthLookupData,
    PacienteAuthLookupDTO,
    PacientePasskeyData,
    PacientePasskeyDTO,
)
from src.modules.identity.application.ports.identity_writer_port import (
    IdentityWriterPort,
)
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.application.ports.shift_policy_reader_port import (
    ShiftPolicyDTO,
    ShiftPolicyReaderPort,
)
from src.modules.queue.application.ports.triage_port import (
    TriageEvaluationDTO,
    TriagePort,
)
from src.modules.scheduling.application.ports.attendance_lookup_port import (
    AttendanceLookupPort,
    AttendanceSnapshot,
)
from src.modules.scheduling.application.ports.scheduling_repository_port import (
    SchedulingRepositoryPort,
)
from src.modules.scheduling.domain.models import (
    AgendaDisponibilidade,
    Agendamento,
    StatusAgendamento,
)
from src.modules.telemetry.application.dtos import PainelTelemetriaDTO
from src.modules.telemetry.application.ports.config_plantao_port import (
    ConfigPlantaoRepositoryPort,
)
from src.modules.telemetry.application.ports.telemetry_cache_port import (
    TelemetryCachePort,
)
from src.modules.telemetry.application.ports.telemetry_reader_port import (
    TelemetryReaderPort,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao
from src.modules.triage.application.ports.emergency_notifier import (
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)


class FakeNoneMappings:
    """Helper mappings returning None for first()."""

    def first(self) -> None:
        return None

    def one_or_none(self) -> None:
        return None

    def all(self) -> list[dict[str, Any]]:
        return []


class FakeMappings:
    """Scripted mappings returning rows for all(), first(), and one_or_none()."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeScalarResult:
    """Scripted scalar result supporting all(), first(), and one_or_none()."""

    def __init__(self, value: Any) -> None:
        self._value: Any = value

    def all(self) -> list[Any]:
        if isinstance(self._value, list):
            return list(cast("list[Any]", self._value))
        if self._value is None:
            return []
        return [self._value]

    def first(self) -> Any:
        if isinstance(self._value, list):
            items = cast("list[Any]", self._value)
            return items[0] if items else None
        return self._value

    def one_or_none(self) -> Any:
        if isinstance(self._value, list):
            items = cast("list[Any]", self._value)
            return items[0] if items else None
        return self._value


class FakeResult:
    """Scripted session result supporting scalar and mappings access."""

    def __init__(
        self,
        value: Any = None,
        *,
        mappings_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._value = value
        self._mappings_rows = mappings_rows

    def scalar(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        assert self._value is not None
        return self._value

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._value)

    def mappings(self) -> FakeMappings | FakeNoneMappings:
        if self._mappings_rows is not None:
            return FakeMappings(self._mappings_rows)
        return FakeNoneMappings()


class FakeAddedResult:
    """Reload-after-commit result returning the first added entity."""

    def __init__(self, added: list[Any]) -> None:
        self._added = added

    def scalar_one_or_none(self) -> Any:
        return self._added[0] if self._added else None

    def scalar_one(self) -> Any:
        assert self._added
        return self._added[0]

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._added)


class FakeAsyncSession:
    """Scripted in-memory async session with ordered execute results."""

    def __init__(
        self,
        results: list[Any] | None = None,
        added: list[Any] | None = None,
        entities: dict[Any, Any] | None = None,
        *,
        commit_error: Exception | None = None,
        flush_error: Exception | None = None,
    ) -> None:
        self._results: list[Any] = list(results) if results is not None else []
        self.added: list[Any] = added if added is not None else []
        self._entities: dict[Any, Any] = dict(entities) if entities is not None else {}
        self.commit_error = commit_error
        self.flush_error = flush_error
        self.commits: int = 0
        self.rollbacks: int = 0
        self.savepoint_rollbacks: int = 0
        self.flushes: int = 0
        self.executes: int = 0
        self.refreshes: int = 0
        self.get_calls: list[dict[str, Any]] = []
        self.executed_sql: list[tuple[str, Any]] = []

    async def get(self, entity_cls: Any, ident: Any, *args: Any, **kwargs: Any) -> Any:
        self.get_calls.append(
            {
                "entity_cls": entity_cls,
                "ident": ident,
                "with_for_update": kwargs.get("with_for_update"),
            }
        )
        if ident in self._entities:
            return self._entities[ident]
        if (entity_cls, ident) in self._entities:
            return self._entities[(entity_cls, ident)]
        for obj in self.added:
            if getattr(obj, "id", None) == ident:
                return obj
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.executes += 1
        if args:
            self.executed_sql.append((str(args[0]), args[1] if len(args) > 1 else None))
        if self._results:
            return self._results.pop(0)
        return FakeResult(None)

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if hasattr(obj, "id"):
            self._entities[obj.id] = obj

    def add_all(self, objs: list[Any]) -> None:
        for obj in objs:
            self.add(obj)

    async def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error
        self.flushes += 1
        return None

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, obj: Any) -> None:
        self.refreshes += 1
        return None

    @asynccontextmanager
    async def begin_nested(self) -> AsyncGenerator["FakeAsyncSession", None]:
        snapshot_added = list(self.added)
        snapshot_entities = dict(self._entities)
        try:
            yield self
        except Exception:
            self.added = snapshot_added
            self._entities = snapshot_entities
            self.savepoint_rollbacks += 1
            raise


class FakePubSub:
    """Thread-safe in-memory Pub/Sub double for forward_pubsub_to_websocket."""

    def __init__(self, queues: dict[str, queue_module.Queue[str]]) -> None:
        self._queues = queues
        self._channel: str | None = None

    async def subscribe(self, channel: str) -> None:
        self._channel = channel
        if channel not in self._queues:
            self._queues[channel] = queue_module.Queue()

    async def listen(self) -> AsyncGenerator[dict[str, object], None]:
        assert self._channel is not None
        q = self._queues[self._channel]
        while True:
            try:
                data = q.get_nowait()
            except queue_module.Empty:
                await asyncio.sleep(0.01)
                continue
            yield {"type": "message", "data": data}

    async def unsubscribe(self, channel: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class FakePipeline:
    """In-memory Redis pipeline double buffering queued operations and results."""

    def __init__(self, valkey: "FakeValkey") -> None:
        self._valkey = valkey
        self._ops: list[Callable[[], Any]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def delete(self, *keys: str) -> "FakePipeline":
        self._ops.append(lambda: self._valkey.delete_sync(*keys))
        return self

    def set(self, key: str, value: Any, *args: Any, **kwargs: Any) -> "FakePipeline":
        nx = bool(kwargs.get("nx", False))
        self._ops.append(lambda: self._valkey.set_sync(key, value, nx=nx))
        return self

    def get(self, key: str) -> "FakePipeline":
        self._ops.append(lambda: self._valkey._kv.get(key))  # pyright: ignore[reportPrivateUsage]
        return self

    def exists(self, *keys: str) -> "FakePipeline":
        self._ops.append(lambda: self._valkey.exists_sync(*keys))
        return self

    def zadd(
        self,
        name: str,
        mapping: dict[str, float | int],
        nx: bool = False,
    ) -> "FakePipeline":
        self._ops.append(lambda: self._valkey.zadd_sync(name, mapping, nx=nx))
        return self

    def zscore(self, name: str, member: str) -> "FakePipeline":
        self._ops.append(lambda: self._valkey.zscore_sync(name, member))
        return self

    def zrank(self, name: str, member: str) -> "FakePipeline":
        self._ops.append(lambda: self._valkey.zrank_sync(name, member))
        return self

    def zcard(self, name: str) -> "FakePipeline":
        self._ops.append(lambda: len(self._valkey._zsets.get(name, {})))  # pyright: ignore[reportPrivateUsage]
        return self

    async def execute(self) -> list[Any]:
        ops = list(self._ops)
        self._ops.clear()
        return [op() for op in ops]


class FakeValkey:
    """Minimal Valkey double supporting pubsub, sorted sets, locks, and pipelines."""

    def __init__(self) -> None:
        self._queues: dict[str, queue_module.Queue[str]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._kv: dict[str, Any] = {}
        self._ttl: dict[str, int] = {}
        self._sets: dict[str, set[str]] = {}

    def delete_sync(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._kv:
                del self._kv[key]
                self._ttl.pop(key, None)
                deleted += 1
        return deleted

    def delete_key(self, key: str) -> None:
        self._kv.pop(key, None)

    def set_sync(self, key: str, value: Any, *, nx: bool = False) -> bool:
        if nx and key in self._kv:
            return False
        self._kv[key] = value
        return True

    def set_key(self, key: str, value: Any) -> None:
        self._kv[key] = value

    def exists_sync(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._kv or name in self._sets or name in self._zsets:
                count += 1
        return count

    def zadd_sync(
        self,
        name: str,
        mapping: dict[str, float | int],
        *,
        nx: bool = False,
    ) -> int:
        if name not in self._zsets:
            self._zsets[name] = {}
        added = 0
        for member, score in mapping.items():
            exists_already = member in self._zsets[name]
            if nx and exists_already:
                continue
            if not exists_already:
                added += 1
            self._zsets[name][member] = float(score)
        return added

    def zscore_sync(self, name: str, member: str) -> float | None:
        if name not in self._zsets:
            return None
        return self._zsets[name].get(member)

    def zrank_sync(self, name: str, member: str) -> int | None:
        if name not in self._zsets or member not in self._zsets[name]:
            return None
        sorted_members = sorted(
            self._zsets[name].items(), key=lambda item: (item[1], item[0])
        )
        for rank, (m, _) in enumerate(sorted_members):
            if m == member:
                return rank
        return None

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    async def get(self, name: str) -> Any:
        return self._kv.get(name)

    async def getdel(self, name: str) -> Any:
        return self._kv.pop(name, None)

    async def delete(self, *names: str) -> int:
        return self.delete_sync(*names)

    async def exists(self, *names: str) -> int:
        return self.exists_sync(*names)

    async def set(self, name: str, value: Any, *args: Any, **kwargs: Any) -> bool:
        stored = self.set_sync(name, value, nx=bool(kwargs.get("nx", False)))
        if stored and "ex" in kwargs and kwargs["ex"] is not None:
            self._ttl[name] = int(kwargs["ex"])
        return stored

    async def ttl(self, name: str) -> int:
        if name not in self._kv:
            return -2
        return self._ttl.get(name, -1)

    async def incr(self, name: str, amount: int = 1) -> int:
        cur = int(self._kv.get(name, 0) or 0)
        self._kv[name] = cur + amount
        return cur + amount

    async def decr(self, name: str, amount: int = 1) -> int:
        cur = int(self._kv.get(name, 0) or 0)
        self._kv[name] = cur - amount
        return cur - amount

    async def expire(self, name: str, time: int) -> bool:
        return True

    async def sadd(self, name: str, *values: str) -> int:
        s = self._sets.setdefault(name, set())
        before = len(s)
        s.update(values)
        return len(s) - before

    async def srem(self, name: str, *values: str) -> int:
        s = self._sets.get(name)
        if s is not None:
            before = len(s)
            s.difference_update(values)
            return before - len(s)
        return 0

    async def scard(self, name: str) -> int:
        s = self._sets.get(name)
        return len(s) if s is not None else 0

    def set_members(self, name: str) -> set[str]:
        return set(self._sets.get(name, set()))

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self._queues)

    async def publish(self, channel: str, message: str) -> int:
        if channel not in self._queues:
            self._queues[channel] = queue_module.Queue()
        self._queues[channel].put(message)
        return 1

    async def zadd(
        self,
        name: str,
        mapping: dict[str, float | int],
        *args: Any,
        **kwargs: Any,
    ) -> int:
        return self.zadd_sync(name, mapping, nx=bool(kwargs.get("nx", False)))

    async def zscore(self, name: str, member: str) -> float | None:
        return self.zscore_sync(name, member)

    async def zrank(self, name: str, member: str) -> int | None:
        return self.zrank_sync(name, member)

    async def zrange(self, name: str, start: int, stop: int) -> list[str]:
        if name not in self._zsets:
            return []
        sorted_members = [
            m
            for m, _ in sorted(
                self._zsets[name].items(), key=lambda item: (item[1], item[0])
            )
        ]
        if stop < 0:
            end = len(sorted_members) + stop + 1
            return sorted_members[start : max(0, end)]
        return sorted_members[start : stop + 1]

    async def zcard(self, name: str) -> int:
        if name not in self._zsets:
            return 0
        return len(self._zsets[name])

    async def zrem(self, name: str, *members: str) -> int:
        if name not in self._zsets:
            return 0
        removed = 0
        for m in members:
            if m in self._zsets[name]:
                del self._zsets[name][m]
                removed += 1
        return removed


class FakeLuaValkeyClient(FakeValkey):
    """In-memory Valkey double supporting scripted script_load, evalsha, and eval."""

    def __init__(
        self,
        *,
        evalsha_outcomes: Sequence[object] = (),
        script_load_outcomes: Sequence[str | Exception] = (),
        eval_outcomes: Sequence[object] = (),
    ) -> None:
        super().__init__()
        self.evalsha_outcomes: list[object] = list(evalsha_outcomes)
        self.script_load_outcomes: list[str | Exception] = list(script_load_outcomes)
        self.eval_outcomes: list[object] = list(eval_outcomes)
        self.script_load_calls: list[str] = []
        self.evalsha_calls: list[tuple[str, int, tuple[object, ...]]] = []
        self.eval_calls: list[tuple[str, int, tuple[object, ...]]] = []

    async def script_load(self, script: str) -> str:
        self.script_load_calls.append(script)
        if self.script_load_outcomes:
            outcome = self.script_load_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return hashlib.sha1(script.encode("utf-8")).hexdigest()  # noqa: S324

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: object) -> object:
        self.evalsha_calls.append((sha, numkeys, keys_and_args))
        if self.evalsha_outcomes:
            outcome = self.evalsha_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return None

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        self.eval_calls.append((script, numkeys, keys_and_args))
        if self.eval_outcomes:
            outcome = self.eval_outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return None


class FakePDFGenerator:
    """In-memory PDF generator double implementing PDFGeneratorPort."""

    def __init__(self, content: bytes = b"%PDF-1.4 Fake PDF Content") -> None:
        self.content = content
        self.payloads: list[Any] = []
        self.calls: int = 0

    def gerar_pdf(self, payload: Any) -> bytes:
        self.calls += 1
        self.payloads.append(payload)
        return self.content


class FakeICPBrasilSigner:
    """In-memory ICP-Brasil digital signer double implementing ICPBrasilSignerPort."""

    def __init__(self, signed_suffix: bytes = b"\n%%SIGNED_ICP_BRASIL%%") -> None:
        self.signed_suffix = signed_suffix
        self.calls: list[tuple[bytes, Any, Any]] = []

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: Any,
        metadata: Any = None,
    ) -> bytes:
        self.calls.append((pdf_bytes, credenciais, metadata))
        return pdf_bytes + self.signed_suffix


class FakeMemoryStorage:
    """In-memory Object Storage double implementing StoragePort."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    async def salvar_documento(
        self,
        chave: str,
        conteudo: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        self._storage[chave] = conteudo
        return chave

    async def obter_documento(self, chave: str) -> bytes:
        if chave not in self._storage:
            from src.modules.consultation.domain.exceptions import (
                DocumentoNaoEncontradoNoStorageError,
            )

            raise DocumentoNaoEncontradoNoStorageError(
                f"Documento com chave '{chave}' não encontrado no storage."
            )
        return self._storage[chave]

    async def gerar_url_pre_assinada(
        self,
        chave: str,
        expiracao_segundos: int = 300,
    ) -> str:
        if chave not in self._storage:
            from src.modules.consultation.domain.exceptions import (
                DocumentoNaoEncontradoNoStorageError,
            )

            raise DocumentoNaoEncontradoNoStorageError(
                f"Documento com chave '{chave}' não encontrado no storage."
            )
        return f"https://mock-storage.local/{chave}?expires={expiracao_segundos}"

    def contains(self, chave: str) -> bool:
        return chave in self._storage

    def clear(self) -> None:
        self._storage.clear()


class FakeArqJob:
    """In-memory ARQ Job double."""

    def __init__(self, job_id: str = "test_job_123") -> None:
        self.job_id = job_id


class FakeArqPool:
    """In-memory ARQ Redis Pool double."""

    def __init__(
        self,
        default_job_id: str = "test_job_123",
        *,
        error: Exception | None = None,
    ) -> None:
        self.default_job_id = default_job_id
        self.error = error
        self.enqueued_jobs: list[dict[str, Any]] = []

    async def enqueue_job(
        self, function_name: str, *args: Any, **kwargs: Any
    ) -> FakeArqJob:
        if self.error is not None:
            raise self.error
        self.enqueued_jobs.append(
            {"function": function_name, "args": args, "kwargs": kwargs}
        )
        return FakeArqJob(job_id=self.default_job_id)


class FakeElegibilidadeNotifier:
    """In-memory double for ElegibilidadeNotifierPort."""

    def __init__(self) -> None:
        self.eventos_falha: list[Any] = []

    async def notificar_falha(self, evento: Any) -> None:
        self.eventos_falha.append(evento)


class FakeEligibilityProvider:
    """In-memory double for EligibilityProviderPort."""

    def __init__(self, resultado: Any) -> None:
        self.resultado = resultado
        self.requisicoes: list[Any] = []

    async def verificar_elegibilidade(self, requisicao: Any) -> Any:
        self.requisicoes.append(requisicao)
        return self.resultado


class FakeAuditTrail:
    """In-memory test double implementing AuditTrailPort (ADR-007)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def record_event(
        self,
        *,
        ator_tipo: AtorTipo | str,
        ator_papel: AtorPapel | str,
        tipo_evento: str,
        atendimento_id: UUID | None = None,
        ator_id: UUID | None = None,
        estado_anterior: str | None = None,
        novo_estado: str | None = None,
        tcle_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        ip_origem: str | None = None,
    ) -> UUID:
        event = AuditEvent(
            atendimento_id=atendimento_id,
            ator_tipo=ator_tipo,
            ator_papel=ator_papel,
            tipo_evento=tipo_evento,
            ator_id=ator_id,
            estado_anterior=estado_anterior,
            novo_estado=novo_estado,
            tcle_hash=tcle_hash,
            payload=payload,
            ip_origem=ip_origem,
        )
        self.events.append(
            {
                "id": event.id,
                "atendimento_id": event.atendimento_id,
                "ator_tipo": event.ator_tipo,
                "ator_papel": event.ator_papel,
                "tipo_evento": event.tipo_evento,
                "ator_id": event.ator_id,
                "estado_anterior": event.estado_anterior,
                "novo_estado": event.novo_estado,
                "tcle_hash": event.tcle_hash,
                "payload": event.payload,
                "ip_origem": event.ip_origem,
            }
        )
        return event.id

    def get_events_by_type(self, tipo_evento: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["tipo_evento"] == tipo_evento]

    def clear(self) -> None:
        self.events.clear()


class FakeAtendimentoReader(AtendimentoReaderPort):
    """In-memory fake implementation of AtendimentoReaderPort for testing."""

    def __init__(
        self,
        resumo: AtendimentoResumoDTO | None = None,
        error_obter_resumo: Exception | None = None,
        error_concluir_atendimento: Exception | None = None,
    ) -> None:
        self.resumo = resumo
        self.error_obter_resumo = error_obter_resumo
        self.error_concluir_atendimento = error_concluir_atendimento
        self.chamada_atendida = False
        self.atendimento_concluido = False
        self.last_auto_commit: bool | None = None
        self.liberados_consulta: list[UUID] = []
        self.obter_resumo_calls: list[UUID] = []

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        self.obter_resumo_calls.append(atendimento_id)
        if self.error_obter_resumo is not None:
            raise self.error_obter_resumo
        if self.resumo is not None and self.resumo.atendimento_id == atendimento_id:
            return self.resumo
        return None

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> UUID | None:
        self.last_auto_commit = auto_commit
        if self.error_concluir_atendimento is not None:
            raise self.error_concluir_atendimento
        self.atendimento_concluido = True
        if self.resumo is not None and self.resumo.atendimento_id == atendimento_id:
            return self.resumo.medico_id
        return None

    async def liberar_consulta_ativa_medico(self, medico_id: UUID) -> None:
        self.liberados_consulta.append(medico_id)

    async def atender_chamada(self, atendimento_id: UUID) -> None:
        self.chamada_atendida = True
        if self.resumo is not None and self.resumo.atendimento_id == atendimento_id:
            self.resumo = AtendimentoResumoDTO(
                atendimento_id=self.resumo.atendimento_id,
                medico_id=self.resumo.medico_id,
                paciente_id=self.resumo.paciente_id,
                status="EM_ATENDIMENTO",
                tcle_hash=self.resumo.tcle_hash,
                is_terminal=self.resumo.is_terminal,
                chamada_iniciada_em=self.resumo.chamada_iniciada_em,
                criado_em=self.resumo.criado_em,
            )


def _matches_cadsus_candidate(
    p: PacienteAuthLookupDTO,
    *,
    cpf: str | None,
    data_nascimento: date | None,
    cns: str | None,
    nome_mae: str | None,
) -> bool:
    if cpf is not None and p.cpf != cpf:
        return False
    if cns is not None and p.cns != cns:
        return False
    if data_nascimento is not None and p.data_nascimento != data_nascimento:
        return False
    if nome_mae is not None and nome_mae.strip():
        if p.nome_mae is None:
            return False
        if p.nome_mae.strip().lower() != nome_mae.strip().lower():
            return False
    return True


class FakeIdentityReader(IdentityReaderPort):
    """Canonical in-memory read-only test double implementing IdentityReaderPort."""

    def __init__(
        self,
        paciente: PacienteAuthLookupDTO | None = None,
        pacientes: Sequence[PacienteAuthLookupDTO] | None = None,
        diretorio: IdentityDirectoryDTO | None = None,
        modo_sus: bool = False,
    ) -> None:
        self.paciente: PacienteAuthLookupDTO | None = paciente
        self.pacientes: Sequence[PacienteAuthLookupDTO] | None = pacientes
        self.diretorio = diretorio
        self.modo_sus = modo_sus
        self.lookups: list[dict[str, object]] = []
        self.passkeys: dict[str, PacientePasskeyData] = {}

    async def obter_dados_diretorio(
        self,
        medico_id: UUID,
        paciente_id: UUID,
    ) -> IdentityDirectoryDTO:
        if self.diretorio is not None:
            return self.diretorio
        return IdentityDirectoryDTO(
            organizacao_nome="Unidade Teste",
            organizacao_cnpj=None,
            medico_id=medico_id,
            medico_nome="Dr. Teste",
            medico_crm="123456",
            medico_crm_uf="SP",
            paciente_id=paciente_id,
            paciente_nome="Paciente Teste",
            paciente_cpf="00011122233",
            paciente_data_nascimento=None,
            paciente_endereco=None,
        )

    async def obter_modo_sus(self) -> bool:
        return self.modo_sus

    async def buscar_paciente_por_telefone(
        self,
        telefone: str,
        cpf: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        self.lookups.append(
            {
                "telefone": telefone,
                "cpf": cpf,
            }
        )
        if self.pacientes is not None:
            for p in self.pacientes:
                if p.telefone == telefone and (cpf is None or p.cpf == cpf):
                    return p
            return None
        return self.paciente

    async def buscar_paciente_cadsus(
        self,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
        nome_mae: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        self.lookups.append(
            {
                "cpf": cpf,
                "data_nascimento": data_nascimento,
                "cns": cns,
                "nome_mae": nome_mae,
            }
        )
        clean_cpf = cpf.strip() if cpf and cpf.strip() else None
        clean_cns = cns.strip() if cns and cns.strip() else None
        if clean_cpf is None and clean_cns is None:
            raise ValidationError(
                "Consulta CADSUS requer ao menos CPF ou CNS informado "
                f"(recebido cpf={cpf!r}, cns={cns!r})."
            )

        candidates = (
            list(self.pacientes)
            if self.pacientes is not None
            else ([self.paciente] if self.paciente is not None else [])
        )
        matches = [
            p
            for p in candidates
            if _matches_cadsus_candidate(
                p,
                cpf=clean_cpf,
                data_nascimento=data_nascimento,
                cns=clean_cns,
                nome_mae=nome_mae,
            )
        ]
        if len(matches) > 1:
            raise ConflictError(
                "Consulta CADSUS retornou múltiplos registros ambíguos; "
                "informe CPF ou CNS único junto ao segundo fator civil."
            )
        return matches[0] if matches else None

    async def buscar_paciente_por_id(
        self,
        paciente_id: UUID,
    ) -> PacienteAuthLookupDTO | None:
        if self.pacientes is not None:
            for p in self.pacientes:
                if p.id == paciente_id:
                    return p
            return None
        if self.paciente is not None and self.paciente.id == paciente_id:
            return self.paciente
        return None

    async def buscar_passkey_por_credencial(
        self,
        credential_id: str,
    ) -> PacientePasskeyDTO | None:
        return self.passkeys.get(credential_id)

    async def listar_passkeys_paciente(
        self,
        paciente_id: UUID,
    ) -> Sequence[PacientePasskeyDTO]:
        return [p for p in self.passkeys.values() if p.paciente_id == paciente_id]


class FakeProducaoAmbulatorialPort(ProducaoAmbulatorialPort):
    """Canonical in-memory test double implementing ProducaoAmbulatorialPort."""

    def __init__(self, error: Exception | None = None) -> None:
        self.consolidacoes: list[dict[str, Any]] = []
        self.error = error

    async def consolidar_teleconsulta(
        self,
        *,
        atendimento_id: UUID,
        profissional_id: UUID,
        paciente_id: UUID,
        cnes: str | None = None,
        codigo_sigtap: str = "03.01.01.025-0",
        carater_atendimento: str = "02",
    ) -> None:
        if self.error is not None:
            raise self.error
        self.consolidacoes.append(
            {
                "atendimento_id": atendimento_id,
                "profissional_id": profissional_id,
                "paciente_id": paciente_id,
                "cnes": cnes,
                "codigo_sigtap": codigo_sigtap,
                "carater_atendimento": carater_atendimento,
            }
        )


class FakeEmergencyNotifier(EmergencyNotifierPort):
    """Canonical in-memory test double replacing production buffer on adapter."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.sent_alerts: list[EmergencyAlertDTO] = []
        self.error = error

    async def notificar_emergencia_samu(self, alert: EmergencyAlertDTO) -> None:
        if self.error is not None:
            raise self.error
        self.sent_alerts.append(alert)

    def clear(self) -> None:
        self.sent_alerts.clear()


class FakeTriagePort(TriagePort):
    """Canonical in-memory test double implementing unified TriagePort."""

    def __init__(
        self,
        evaluation: TriageEvaluationDTO,
        triagem_id: UUID | None = None,
        *,
        queixas: dict[UUID, str | None] | None = None,
    ) -> None:
        self.evaluation = evaluation
        self.triagem_id = triagem_id or uuid7()
        self.queixas: dict[UUID, str | None] = queixas or {}
        self.avaliacoes: list[dict[str, Any]] = []
        self.triagens_registradas: list[dict[str, Any]] = []
        self.error_avaliar: Exception | None = None
        self.error_registrar: Exception | None = None

    async def avaliar_risco(
        self,
        queixa_principal: str,
        sintomas: Sequence[str],
        escala_dor: int = 0,
        tcle_texto: str = "",
        tcle_hash: str | None = None,
        *,
        raise_on_emergency: bool = True,
        atendimento_id: UUID | None = None,
    ) -> TriageEvaluationDTO:
        self.avaliacoes.append(
            {
                "queixa_principal": queixa_principal,
                "sintomas": list(sintomas),
                "escala_dor": escala_dor,
                "tcle_texto": tcle_texto,
                "tcle_hash": tcle_hash,
                "raise_on_emergency": raise_on_emergency,
                "atendimento_id": atendimento_id,
            }
        )
        if self.error_avaliar is not None:
            raise self.error_avaliar
        return self.evaluation

    async def registrar_triagem(
        self,
        atendimento_id: UUID,
        queixa_principal: str,
        sintomas: Sequence[str],
        prioridade_calculada: int | None = None,
        alerta_samu_disparado: bool = False,
        escala_dor: int = 0,
    ) -> UUID:
        if self.error_registrar is not None:
            raise self.error_registrar
        self.triagens_registradas.append(
            {
                "atendimento_id": atendimento_id,
                "queixa_principal": queixa_principal,
                "sintomas": list(sintomas),
                "prioridade_calculada": prioridade_calculada,
                "alerta_samu_disparado": alerta_samu_disparado,
                "escala_dor": escala_dor,
            }
        )
        return self.triagem_id

    async def obter_queixas_por_atendimentos(
        self,
        atendimento_ids: Sequence[UUID],
    ) -> dict[UUID, str | None]:
        return {aid: self.queixas.get(aid) for aid in atendimento_ids}


class FakeShiftPolicyReader(ShiftPolicyReaderPort):
    """Canonical in-memory ShiftPolicyReaderPort double."""

    def __init__(self, policy: ShiftPolicyDTO | None = None) -> None:
        self.policy = policy or ShiftPolicyDTO()

    async def obter_politica_atual(self) -> ShiftPolicyDTO:
        return self.policy


class FakeQueueEngine(QueueEnginePort):
    """Canonical stateful in-memory QueueEnginePort double for queue & worker tests."""

    def __init__(
        self,
        *,
        medicos_ativos: set[UUID] | None = None,
        cota_diaria_usada: int = 0,
        forced_codigo: AlocacaoCodigo | None = None,
        forced_next_id: UUID | None = None,
    ) -> None:
        self.fila_scores: dict[UUID, int] = {}
        self.locks_medico: dict[UUID, UUID] = {}
        self.locks_atendimento: dict[UUID, UUID] = {}
        self.locks_consulta_ativa: dict[UUID, UUID] = {}
        self.medicos_ativos: set[UUID] = set(medicos_ativos or ())
        self.cota_diaria_usada: int = cota_diaria_usada
        self.sweeper_lock_held: bool = False
        self.published_fila: list[tuple[UUID, dict[str, object]]] = []
        self.published_medico: list[tuple[UUID, dict[str, object]]] = []
        self.forced_codigo = forced_codigo
        self.forced_next_id = forced_next_id
        self.alocar_atendimento_calls: list[dict[str, object]] = []
        self.alocar_proximo_calls: list[dict[str, object]] = []
        self.sweeper_checks: int = 0

    def _sorted_ids(self) -> list[UUID]:
        return sorted(
            self.fila_scores.keys(),
            key=lambda aid: (self.fila_scores[aid], str(aid)),
        )

    async def alocar_proximo(
        self,
        medico_id: UUID,
        ttl_segundos: int = 45,
        max_scan: int = 50,
    ) -> tuple[AlocacaoCodigo, UUID | None]:
        self.alocar_proximo_calls.append(
            {
                "medico_id": medico_id,
                "ttl_segundos": ttl_segundos,
                "max_scan": max_scan,
            }
        )
        if self.forced_codigo is not None:
            return self.forced_codigo, self.forced_next_id
        if medico_id in self.locks_medico or medico_id in self.locks_consulta_ativa:
            return AlocacaoCodigo.MEDICO_OCUPADO, None
        for cand in self._sorted_ids()[:max_scan]:
            if cand not in self.locks_atendimento:
                self.fila_scores.pop(cand, None)
                self.locks_medico[medico_id] = cand
                self.locks_atendimento[cand] = medico_id
                return AlocacaoCodigo.SUCESSO, cand
        return AlocacaoCodigo.INDISPONIVEL, None

    async def alocar_atendimento(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int = 45,
    ) -> AlocacaoCodigo:
        self.alocar_atendimento_calls.append(
            {
                "medico_id": medico_id,
                "atendimento_id": atendimento_id,
                "ttl_segundos": ttl_segundos,
            }
        )
        if self.forced_codigo is not None:
            return self.forced_codigo
        if medico_id in self.locks_medico or medico_id in self.locks_consulta_ativa:
            return AlocacaoCodigo.MEDICO_OCUPADO
        if (
            atendimento_id in self.locks_atendimento
            or atendimento_id not in self.fila_scores
        ):
            return AlocacaoCodigo.INDISPONIVEL
        self.fila_scores.pop(atendimento_id, None)
        self.locks_medico[medico_id] = atendimento_id
        self.locks_atendimento[atendimento_id] = medico_id
        return AlocacaoCodigo.SUCESSO

    async def promover_para_consulta(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int = 7200,
    ) -> None:
        self.locks_atendimento.pop(atendimento_id, None)
        self.locks_medico.pop(medico_id, None)
        self.locks_consulta_ativa[medico_id] = atendimento_id

    async def liberar_ring(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> None:
        self.locks_medico.pop(medico_id, None)
        self.locks_atendimento.pop(atendimento_id, None)

    async def liberar_consulta(self, medico_id: UUID) -> None:
        self.locks_consulta_ativa.pop(medico_id, None)

    async def devolver_para_fila(
        self,
        atendimento_id: UUID,
        score: int,
        medico_id: UUID | None = None,
        *,
        nx: bool = False,
    ) -> bool:
        self.locks_atendimento.pop(atendimento_id, None)
        if medico_id is not None:
            self.locks_medico.pop(medico_id, None)
        if nx and atendimento_id in self.fila_scores:
            return False
        self.fila_scores[atendimento_id] = score
        return True

    async def inserir_ou_atualizar_fila(
        self,
        atendimento_id: UUID,
        score: int,
        *,
        nx: bool = False,
    ) -> int | None:
        if not (nx and atendimento_id in self.fila_scores):
            self.fila_scores[atendimento_id] = score
        ordered = self._sorted_ids()
        return ordered.index(atendimento_id) if atendimento_id in ordered else None

    async def remover_da_fila(self, atendimento_id: UUID) -> bool:
        return self.fila_scores.pop(atendimento_id, None) is not None

    async def obter_posicao_e_tamanho(
        self,
        atendimento_id: UUID,
    ) -> tuple[int | None, int]:
        ordered = self._sorted_ids()
        rank = ordered.index(atendimento_id) if atendimento_id in ordered else None
        return rank, len(ordered)

    async def obter_tamanho_fila(self) -> int:
        return len(self.fila_scores)

    async def consumir_cota_ou_bloquear(
        self,
        cota_diaria_maxima: int | None,
    ) -> tuple[bool, int]:
        self.cota_diaria_usada += 1
        if (
            cota_diaria_maxima is not None
            and self.cota_diaria_usada > cota_diaria_maxima
        ):
            self.cota_diaria_usada = max(0, self.cota_diaria_usada - 1)
            return False, self.cota_diaria_usada
        return True, self.cota_diaria_usada

    async def estornar_cota_diaria(self) -> None:
        self.cota_diaria_usada = max(0, self.cota_diaria_usada - 1)

    async def registrar_medico_ativo(self, medico_id: UUID) -> None:
        self.medicos_ativos.add(medico_id)

    async def desregistrar_medico_ativo(self, medico_id: UUID) -> None:
        self.medicos_ativos.discard(medico_id)

    async def obter_medicos_ativos_count(self) -> int:
        return len(self.medicos_ativos)

    async def publicar_evento_fila(
        self,
        atendimento_id: UUID,
        payload: dict[str, object],
    ) -> None:
        self.published_fila.append((atendimento_id, dict(payload)))

    async def publicar_evento_medico(
        self,
        medico_id: UUID,
        payload: dict[str, object],
    ) -> None:
        self.published_medico.append((medico_id, dict(payload)))

    async def adquirir_lock_sweeper(self, ttl_segundos: int = 55) -> bool:
        if self.sweeper_lock_held:
            return False
        self.sweeper_lock_held = True
        return True

    async def liberar_lock_sweeper(self) -> None:
        self.sweeper_lock_held = False

    async def esta_bloqueado_para_reconciliacao(
        self,
        atendimento_id: UUID,
        medico_id: UUID | None,
    ) -> bool:
        self.sweeper_checks += 1
        if atendimento_id in self.fila_scores:
            return True
        if atendimento_id in self.locks_atendimento:
            return True
        return medico_id is not None and (
            self.locks_medico.get(medico_id) == atendimento_id
            or self.locks_consulta_ativa.get(medico_id) == atendimento_id
        )


class FakePasswordHasher(PasswordHasherPort):
    """Canonical deterministic hasher double implementing PasswordHasherPort."""

    def __init__(self, prefix: str = "$argon2id$fake$") -> None:
        self._prefix = prefix
        self.dummy_calls = 0
        self.hash_calls = 0

    def hash(self, password: str) -> str:
        self.hash_calls += 1
        return f"{self._prefix}{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        expected = f"{self._prefix}{plain_password}"
        return hmac.compare_digest(expected, hashed_password)

    def needs_rehash(self, hashed_password: str) -> bool:
        return not hashed_password.startswith(self._prefix)

    def dummy_verify(self) -> None:
        self.dummy_calls += 1


class FakeIdentityWriter(IdentityWriterPort):
    """Canonical in-memory IdentityWriterPort backed by FakeIdentityReader."""

    def __init__(self, reader: FakeIdentityReader) -> None:
        self._reader = reader
        if self._reader.pacientes is None:
            self._reader.pacientes = (
                [self._reader.paciente] if self._reader.paciente is not None else []
            )

    async def criar_paciente(
        self,
        *,
        cpf: str,
        nome_completo: str,
        data_nascimento: date,
        telefone: str,
    ) -> PacienteAuthLookupDTO:
        clean_cpf = re.sub(r"\D", "", cpf)
        items = list(self._reader.pacientes or [])
        for existing in items:
            if existing.cpf == clean_cpf:
                raise ConflictError(
                    "Não foi possível concluir o cadastro com os dados informados. "
                    "Caso já possua conta, utilize a opção Entrar."
                )

        created = PacienteAuthLookupData(
            id=uuid7(),
            telefone=telefone,
            cpf=clean_cpf,
            nome_completo=nome_completo,
            nome_mae=None,
            data_nascimento=data_nascimento,
        )
        items.append(created)
        self._reader.pacientes = items
        return created

    async def registrar_passkey_paciente(
        self,
        paciente_id: UUID,
        credential_id: str,
        public_key: str,
        sign_count: int = 0,
        device_name: str | None = None,
    ) -> PacientePasskeyDTO:
        if credential_id in self._reader.passkeys:
            raise ConflictError(
                f"Credencial WebAuthn '{credential_id}' já registrada na plataforma."
            )
        record = PacientePasskeyData(
            id=uuid7(),
            paciente_id=paciente_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            device_name=device_name,
        )
        self._reader.passkeys[credential_id] = record
        return record

    async def atualizar_sign_count_passkey(
        self,
        credential_id: str,
        novo_sign_count: int,
    ) -> PacientePasskeyDTO:
        existing = self._reader.passkeys.get(credential_id)
        if existing is None:
            raise NotFoundError(
                f"Credencial Passkey '{credential_id}' não encontrada na plataforma."
            )
        if novo_sign_count < 0 or (
            existing.sign_count > 0 and novo_sign_count <= existing.sign_count
        ):
            raise ValidationError(
                f"Contador de assinatura regressivo ou inválido: '{novo_sign_count}'; "
                f"esperado > {existing.sign_count}."
            )
        updated = PacientePasskeyData(
            id=existing.id,
            paciente_id=existing.paciente_id,
            credential_id=existing.credential_id,
            public_key=existing.public_key,
            sign_count=novo_sign_count,
            device_name=existing.device_name,
        )
        self._reader.passkeys[credential_id] = updated
        return updated


class MemoryChallengeStore(InMemoryChallengeStore):
    """Canonical in-memory atomic ChallengeStorePort double with call tracking."""

    def __init__(self) -> None:
        super().__init__()
        self.entries = self._entries
        self.consume_calls: list[str] = []

    async def consume_one_time(self, key: str) -> str | None:
        self.consume_calls.append(key)
        return await super().consume_one_time(key)

    def clear(self) -> None:
        super().clear()
        self.consume_calls.clear()


class FakePatientCredentialRepository(PatientCredentialRepositoryPort):
    """Canonical in-memory PatientCredentialRepositoryPort double."""

    def __init__(self) -> None:
        self.by_key: dict[str, UsuarioCredencial] = {}
        self.identificador_lookups: list[tuple[str, str]] = []
        self.existe_calls: list[str] = []

    async def buscar_por_identificador(
        self,
        identificador: str,
        papel: str = Role.PACIENTE.value,
    ) -> UsuarioCredencial | None:
        self.identificador_lookups.append((identificador, papel))
        cred = self.by_key.get(identificador.strip().lower())
        if cred is None or cred.papel != papel.strip().upper():
            return None
        return cred

    async def buscar_por_usuario_id(
        self,
        usuario_id: UUID,
        papel: str = Role.PACIENTE.value,
    ) -> UsuarioCredencial | None:
        target_papel = papel.strip().upper()
        for cred in self.by_key.values():
            if cred.usuario_id == usuario_id and cred.papel == target_papel:
                return cred
        return None

    async def existe_identificador(
        self,
        identificador: str,
    ) -> bool:
        self.existe_calls.append(identificador)
        return identificador.strip().lower() in self.by_key

    async def criar_credencial(
        self,
        credencial: UsuarioCredencial,
    ) -> UsuarioCredencial:
        key = credencial.identificador
        if key in self.by_key:
            raise ConflictError(
                "Não foi possível concluir o cadastro com os dados informados. "
                "Caso já possua conta, utilize a opção Entrar."
            )
        self.by_key[key] = credencial
        return credencial


class FakeAttendanceLookup(AttendanceLookupPort):
    """Canonical in-memory AttendanceLookupPort double for scheduling tests."""

    def __init__(self) -> None:
        self.atendimentos: dict[UUID, AttendanceSnapshot] = {}
        self.calls: list[UUID] = []

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AttendanceSnapshot | None:
        self.calls.append(atendimento_id)
        return self.atendimentos.get(atendimento_id)


class FakeSchedulingRepository(SchedulingRepositoryPort):
    """Canonical in-memory SchedulingRepositoryPort double."""

    def __init__(self) -> None:
        self.disponibilidades: list[AgendaDisponibilidade] = []
        self.agendamentos: list[Agendamento] = []
        self.last_for_update: bool | None = None
        self.lock_calls: list[tuple[UUID, int]] = []
        self.last_ocupados_profissional_ids: set[UUID] | None = None

    async def listar_disponibilidades_ativas(
        self,
        especialidade: str,
    ) -> Sequence[AgendaDisponibilidade]:
        return [
            d
            for d in self.disponibilidades
            if d.especialidade == especialidade and d.ativo
        ]

    async def listar_agendamentos_ocupados(
        self,
        inicio: datetime,
        fim: datetime,
        profissional_ids: Sequence[UUID],
    ) -> Sequence[Agendamento]:
        ids_set = set(profissional_ids)
        self.last_ocupados_profissional_ids = ids_set
        if not ids_set:
            return []
        inativos = {StatusAgendamento.CANCELADO.value, StatusAgendamento.FALTA.value}
        return [
            a
            for a in self.agendamentos
            if a.profissional_id in ids_set
            and a.status not in inativos
            and a.slot_inicio < fim
            and a.slot_fim > inicio
        ]

    async def buscar_agendamento_conflitante(
        self,
        profissional_id: UUID,
        slot_inicio: datetime,
        slot_fim: datetime,
        *,
        paciente_id: UUID | None = None,
    ) -> Agendamento | None:
        inativos = {StatusAgendamento.CANCELADO.value, StatusAgendamento.FALTA.value}
        for a in self.agendamentos:
            if a.status in inativos:
                continue
            if not (a.slot_inicio < slot_fim and a.slot_fim > slot_inicio):
                continue
            if a.profissional_id == profissional_id or (
                paciente_id is not None and a.paciente_id == paciente_id
            ):
                return a
        return None

    async def adquirir_lock_disponibilidade(
        self,
        profissional_id: UUID,
        dia_semana: int,
    ) -> None:
        self.lock_calls.append((profissional_id, dia_semana))

    async def buscar_disponibilidade_profissional(
        self,
        profissional_id: UUID,
        especialidade: str | None,
        dia_semana: int,
    ) -> Sequence[AgendaDisponibilidade]:
        return [
            d
            for d in self.disponibilidades
            if d.profissional_id == profissional_id
            and (especialidade is None or d.especialidade == especialidade)
            and d.dia_semana == dia_semana
            and d.ativo
        ]

    async def buscar_agendamento_por_id(
        self,
        agendamento_id: UUID,
        for_update: bool = False,
    ) -> Agendamento | None:
        self.last_for_update = for_update
        for a in self.agendamentos:
            if a.id == agendamento_id:
                return a
        return None

    async def listar_agendamentos_paciente(
        self,
        paciente_id: UUID,
    ) -> Sequence[Agendamento]:
        itens = [a for a in self.agendamentos if a.paciente_id == paciente_id]
        return sorted(itens, key=lambda a: a.slot_inicio)

    async def listar_agendamentos_profissional(
        self,
        profissional_id: UUID,
        inicio: datetime,
        fim: datetime,
    ) -> Sequence[Agendamento]:
        itens = [
            a
            for a in self.agendamentos
            if a.profissional_id == profissional_id
            and a.slot_inicio >= inicio
            and a.slot_inicio < fim
        ]
        return sorted(itens, key=lambda a: a.slot_inicio)

    def adicionar_disponibilidade(self, disponibilidade: AgendaDisponibilidade) -> None:
        self.disponibilidades.append(disponibilidade)

    def adicionar_agendamento(self, agendamento: Agendamento) -> None:
        self.agendamentos.append(agendamento)


class FakeBpaDirectory(BpaDirectoryPort):
    """Canonical in-memory BpaDirectoryPort double."""

    def __init__(self, registros: Sequence[BpaRegistroDetalheDTO] = ()) -> None:
        self.registros = list(registros)
        self.calls: list[str] = []

    async def buscar_detalhes_bpa_lote(
        self,
        competencia: str,
    ) -> list[BpaRegistroDetalheDTO]:
        self.calls.append(competencia)
        return list(self.registros)


class FakeTelemetryReader(TelemetryReaderPort):
    """Canonical in-memory TelemetryReaderPort double."""

    def __init__(self, painel: PainelTelemetriaDTO | None = None) -> None:
        self.painel = painel
        self.calls: list[dict[str, Any]] = []

    async def obter_painel_telemetria(
        self,
        config: ConfiguracaoPlantao | None = None,
        data_inicio: datetime | None = None,
    ) -> PainelTelemetriaDTO:
        self.calls.append({"config": config, "data_inicio": data_inicio})
        if self.painel is not None:
            return self.painel
        return PainelTelemetriaDTO(
            gerado_em=datetime.now(UTC),
            tme_medio_segundos=0.0,
            tme_nivel_1_segundos=0.0,
            tme_nivel_2_segundos=0.0,
            tme_nivel_3_segundos=0.0,
            tme_nivel_4_segundos=0.0,
            tme_nivel_5_segundos=0.0,
            tma_medio_segundos=0.0,
            medicos_tma=(),
            no_show_rate=0.0,
            evasao_rate=0.0,
            sla_compliance_percentual=100.0,
            sla_em_conformidade=True,
            medicos_ativos_count=0,
            total_pacientes_fila=0,
            total_atendimentos=0,
        )


class FakeConfigPlantaoRepository(ConfigPlantaoRepositoryPort):
    """Canonical in-memory ConfigPlantaoRepositoryPort double."""

    def __init__(self, config: ConfiguracaoPlantao | None = None) -> None:
        self.config = config
        self.obter_atual_calls: int = 0
        self.obter_ou_criar_calls: int = 0
        self.salvos: list[ConfiguracaoPlantao] = []

    async def obter_atual(self) -> ConfiguracaoPlantao | None:
        self.obter_atual_calls += 1
        return self.config

    async def obter_ou_criar_padrao(self) -> ConfiguracaoPlantao:
        self.obter_ou_criar_calls += 1
        if self.config is None:
            self.config = ConfiguracaoPlantao()
        return self.config

    async def salvar(self, configuracao: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
        self.config = configuracao
        self.salvos.append(configuracao)
        return configuracao


class FakeTelemetryCache(TelemetryCachePort):
    """Canonical in-memory TelemetryCachePort double with call tracking."""

    def __init__(self, initial: PainelTelemetriaDTO | None = None) -> None:
        self.painel: PainelTelemetriaDTO | None = initial
        self.obter_calls: int = 0
        self.salvar_calls: list[tuple[PainelTelemetriaDTO, int]] = []
        self.invalidar_calls: int = 0

    async def obter_painel(self) -> PainelTelemetriaDTO | None:
        self.obter_calls += 1
        return self.painel

    async def salvar_painel(
        self,
        painel: PainelTelemetriaDTO,
        ttl_segundos: int = 60,
    ) -> None:
        self.painel = painel
        self.salvar_calls.append((painel, ttl_segundos))

    async def invalidar_painel(self) -> None:
        self.invalidar_calls += 1
        self.painel = None


class FakeDocumentDirectory:
    """In-memory DocumentDirectoryPort double returning deterministic metadata."""

    def __init__(
        self,
        dados: Any | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        from src.modules.consultation.application.ports.document_directory_port import (
            DadosVerificacaoDirectory,
        )

        self.dados = dados or DadosVerificacaoDirectory(
            organizacao_nome="Unidade SUS Telemedicina",
            medico_nome="Dr. Medico Teste",
            medico_crm="123456",
            medico_crm_uf="SP",
            paciente_nome="Paciente Teste",
            paciente_cpf="111.222.333-44",
            organizacao_cnpj="11222333000144",
            cnes="2695251",
        )
        self.error = error
        self.calls: list[tuple[UUID, UUID]] = []

    async def obter_dados_verificacao(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> Any:
        self.calls.append((medico_id, atendimento_id))
        if self.error is not None:
            raise self.error
        return self.dados


class _FakeS3Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self, session: "FakeS3Session") -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeS3Client":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        self._session.put_calls.append(
            {
                "Bucket": Bucket,
                "Key": Key,
                "Body": Body,
                "ContentType": ContentType,
            }
        )
        self._session.objects[(Bucket, Key)] = Body

    async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self._session.get_calls.append({"Bucket": Bucket, "Key": Key})
        if self._session.get_error is not None:
            raise self._session.get_error
        data = self._session.objects.get((Bucket, Key), b"")
        return {"Body": _FakeS3Body(data)}

    async def generate_presigned_url(
        self,
        *,
        ClientMethod: str,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str:
        self._session.presign_calls.append(
            {
                "ClientMethod": ClientMethod,
                "Params": Params,
                "ExpiresIn": ExpiresIn,
            }
        )
        if self._session.presigned_url is not None:
            return self._session.presigned_url
        bucket = Params.get("Bucket", "bucket")
        key = Params.get("Key", "key")
        return f"https://s3.medisync.local/{bucket}/{key}?ExpiresIn={ExpiresIn}"


class FakeS3Session:
    """In-memory aioboto3 Session replacement for S3StorageAdapter tests."""

    def __init__(
        self,
        *,
        objects: dict[tuple[str, str], bytes] | None = None,
        get_error: Exception | None = None,
        presigned_url: str | None = None,
    ) -> None:
        self.objects: dict[tuple[str, str], bytes] = dict(objects) if objects else {}
        self.get_error = get_error
        self.presigned_url = presigned_url
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.presign_calls: list[dict[str, Any]] = []
        self.client_kwargs: list[dict[str, Any]] = []

    def client(self, service_name: str, **kwargs: Any) -> _FakeS3Client:
        self.client_kwargs.append({"service_name": service_name, **kwargs})
        return _FakeS3Client(self)


class FakeCloudPSCOAuth2Client:
    """In-memory CloudPSCOAuth2Client double signing digests with real CMS or script."""

    def __init__(
        self,
        *,
        cert_info: dict[str, Any] | None = None,
        cms_signature_b64: str | None = None,
        error_on_info: Exception | None = None,
        error_on_sign: Exception | None = None,
    ) -> None:
        self.cert_info = cert_info
        self.cms_signature_b64 = cms_signature_b64
        self.error_on_info = error_on_info
        self.error_on_sign = error_on_sign
        self.info_calls: list[dict[str, Any]] = []
        self.sign_calls: list[dict[str, Any]] = []
        self._key_pem: bytes | None = None
        self._cert_b64: str | None = None

    def _ensure_cert_pair(self) -> tuple[str, bytes]:
        if self._cert_b64 is not None and self._key_pem is not None:
            return self._cert_b64, self._key_pem

        import base64
        from datetime import timedelta

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
                x509.NameAttribute(NameOID.COMMON_NAME, "DR. CLOUD PSC TESTE:123456"),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .sign(key, hashes.SHA256())
        )
        cert_der = cert.public_bytes(serialization.Encoding.DER)
        self._cert_b64 = base64.b64encode(cert_der).decode("ascii")
        self._key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return self._cert_b64, self._key_pem

    async def obter_info_credencial(
        self,
        provider: str,
        token: str,
        credential_id: str | None = None,
    ) -> dict[str, Any]:
        self.info_calls.append(
            {"provider": provider, "token": token, "credential_id": credential_id}
        )
        if self.error_on_info is not None:
            raise self.error_on_info
        if self.cert_info is not None:
            return self.cert_info
        cert_b64, _ = self._ensure_cert_pair()
        return {"cert": {"certificates": [cert_b64]}}

    async def assinar_hash(
        self,
        provider: str,
        token: str,
        credential_id: str,
        hash_b64: str,
        sign_algo: str = "1.2.840.113549.1.1.1",
        response_format: str | None = None,
    ) -> str:
        self.sign_calls.append(
            {
                "provider": provider,
                "token": token,
                "credential_id": credential_id,
                "hash_b64": hash_b64,
                "sign_algo": sign_algo,
                "response_format": response_format,
            }
        )
        if self.error_on_sign is not None:
            raise self.error_on_sign
        if self.cms_signature_b64 is not None:
            return self.cms_signature_b64

        import base64

        from pyhanko.keys.pemder import (
            load_certs_from_pemder_data,
            load_private_key_from_pemder_data,
        )
        from pyhanko.sign import signers
        from pyhanko_certvalidator.registry import SimpleCertificateStore

        cert_b64, key_pem = self._ensure_cert_pair()
        cert_pem = (
            "-----BEGIN CERTIFICATE-----\n" + cert_b64 + "\n-----END CERTIFICATE-----\n"
        ).encode("ascii")
        certs_list = cast(
            "list[asn1_x509.Certificate]",
            list(load_certs_from_pemder_data(cert_pem)),  # pyright: ignore[reportUnknownArgumentType]
        )
        a_cert = certs_list[0]
        a_key: Any = load_private_key_from_pemder_data(key_pem, passphrase=None)
        store = SimpleCertificateStore()
        store.register(a_cert)
        signer = signers.SimpleSigner(
            signing_cert=a_cert, signing_key=a_key, cert_registry=store
        )
        digest_bytes = base64.b64decode(hash_b64)
        cms_obj: Any = await signer.async_sign(  # pyright: ignore[reportUnknownMemberType]
            digest_bytes, digest_algorithm="sha256", use_pades=True
        )
        return base64.b64encode(cast("bytes", cms_obj.dump())).decode("ascii")
