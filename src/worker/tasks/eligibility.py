"""Asynchronous health insurance and SUS eligibility verification task (RF-02, RN03)."""

import logging
from typing import Any
from uuid import UUID

from src.core.context import tenant_context
from src.core.errors import NotFoundError
from src.modules.billing import (
    ElegibilidadeNotifierPort,
    EligibilityProviderPort,
    RequisicaoElegibilidade,
)
from src.modules.billing.composition import build_elegibilidade_service
from src.modules.identity.composition import get_identity_reader
from src.modules.queue.composition import build_fila_service_for_session
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.eligibility")


async def _obter_modo_sus(
    session: Any,
    organizacao_id: int,
    modo_publico_sus: bool | None,
) -> bool:
    if modo_publico_sus is not None:
        return modo_publico_sus
    identity_reader = get_identity_reader(session)
    return await identity_reader.obter_modo_sus(organizacao_id)


async def _promover_atendimento_apto(
    valkey: Any,
    session: Any,
    organizacao_id: int,
    atend_uuid: UUID,
    atendimento_id: str,
    codigo_autorizacao: str | None,
) -> dict[str, Any]:
    fila_service = build_fila_service_for_session(valkey=valkey, session=session)
    try:
        adm_result = await fila_service.admitir_atendimento_apto(
            organizacao_id=organizacao_id,
            atendimento_id=atend_uuid,
        )
    except NotFoundError:
        logger.warning(
            "Attendance %s not found in DB during eligibility promotion",
            atendimento_id,
        )
        return {"status": "not_found", "aprovado": True}

    if adm_result.promovido:
        return {
            "status": "aprovado",
            "aprovado": True,
            "codigo_autorizacao": codigo_autorizacao,
            "score": adm_result.score,
        }
    return {
        "status": "already_promoted",
        "aprovado": True,
        "current_status": adm_result.status,
    }


async def _executar_validacao_elegibilidade(
    *,
    session: Any,
    ctx: dict[str, Any],
    organizacao_id: int,
    atend_uuid: UUID,
    atendimento_id: str,
    paciente_uuid: UUID,
    cpf: str | None,
    cns: str | None,
    operadora_id: str | None,
    numero_carteirinha: str | None,
    modo_publico_sus: bool | None,
    provider: EligibilityProviderPort | None,
    notifier: ElegibilidadeNotifierPort | None,
) -> dict[str, Any]:
    is_sus = await _obter_modo_sus(session, organizacao_id, modo_publico_sus)
    service = build_elegibilidade_service(
        is_sus=bool(is_sus),
        provider=provider,
        notifier=notifier,
    )
    req = RequisicaoElegibilidade(
        organizacao_id=organizacao_id,
        atendimento_id=atend_uuid,
        paciente_id=paciente_uuid,
        cpf=cpf,
        cns=cns,
        operadora_id=operadora_id,
        numero_carteirinha=numero_carteirinha,
    )
    resultado = await service.avaliar_elegibilidade(req)

    if resultado.aprovado:
        valkey = get_valkey_from_ctx(ctx)
        return await _promover_atendimento_apto(
            valkey=valkey,
            session=session,
            organizacao_id=organizacao_id,
            atend_uuid=atend_uuid,
            atendimento_id=atendimento_id,
            codigo_autorizacao=resultado.codigo_autorizacao,
        )

    logger.warning(
        "Eligibility check failed for attendance %s: status=%s motivo=%s",
        atendimento_id,
        resultado.status.value,
        resultado.motivo,
    )
    return {
        "status": resultado.status.value,
        "aprovado": False,
        "motivo": resultado.motivo,
    }


@monitored_task
async def validar_elegibilidade_task(
    ctx: dict[str, Any],
    organizacao_id: int,
    atendimento_id: str,
    paciente_id: str,
    cpf: str | None = None,
    cns: str | None = None,
    operadora_id: str | None = None,
    numero_carteirinha: str | None = None,
    modo_publico_sus: bool | None = None,
    provider: EligibilityProviderPort | None = None,
    notifier: ElegibilidadeNotifierPort | None = None,
) -> dict[str, Any]:
    """Valida elegibilidade (SUS/Convênio) e admite em fila (RN03, RF-02, RF-05).

    Conforma com processamento assíncrono em worker ARQ com admissão resiliente.
    Regras: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
    Decisões: docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md
    """
    atend_uuid = UUID(atendimento_id)
    paciente_uuid = UUID(paciente_id)

    with tenant_context(organizacao_id):
        async with get_db_session_from_ctx(ctx) as session:
            return await _executar_validacao_elegibilidade(
                session=session,
                ctx=ctx,
                organizacao_id=organizacao_id,
                atend_uuid=atend_uuid,
                atendimento_id=atendimento_id,
                paciente_uuid=paciente_uuid,
                cpf=cpf,
                cns=cns,
                operadora_id=operadora_id,
                numero_carteirinha=numero_carteirinha,
                modo_publico_sus=modo_publico_sus,
                provider=provider,
                notifier=notifier,
            )
