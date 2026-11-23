import re
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from src.core.errors import ValidationError
from src.core.uuid7 import uuid7
from src.modules.triage.application.dtos import (
    TriageRiskEvaluationDTO,
)
from src.modules.triage.application.ports.emergency_notifier import (
    INSTRUCAO_SAMU_PADRAO,
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)
from src.modules.triage.domain.classification import (
    calcular_hash_tcle,
    classificar_risco_clinico,
    normalizar_sintomas,
)
from src.modules.triage.domain.exceptions import (
    EmergenciaCriticaSamuError,
    TriagemInvalidaError,
)
from src.modules.triage.domain.models.triagem import Triagem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_TCLE_HASH_REGEX = re.compile(r"^[0-9a-f]{64}$")


def _resolver_tcle_hash(tcle_texto: str, tcle_hash: str | None) -> str:
    if tcle_hash is not None and tcle_hash.strip():
        cleaned = tcle_hash.strip().lower()
        if not _TCLE_HASH_REGEX.match(cleaned):
            raise ValidationError(
                f"Hash TCLE '{tcle_hash}' inválido; esperado digest SHA-256 "
                "hexadecimal de 64 caracteres (formato ^[0-9a-f]{64}$)."
            )
        return cleaned
    if tcle_texto and tcle_texto.strip():
        return calcular_hash_tcle(tcle_texto)
    raise ValidationError(
        "Consentimento TCLE obrigatório (texto ou hash). "
        f"Recebido tcle_texto='{tcle_texto}' e tcle_hash='{tcle_hash}'."
    )


class TriageService:
    """Serviço de avaliação clínica de risco, cálculo de TCLE e bloqueio de emergência.

    Consolida salvaguarda SAMU 192 (RN04) e validação criptográfica de TCLE (RN07).
    Regras: docs/explanation/domains/triage-domain.md.
    História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
    """

    def __init__(
        self,
        emergency_notifier: EmergencyNotifierPort | None = None,
        session: "AsyncSession | None" = None,
    ) -> None:
        self._notifier = emergency_notifier
        self._session = session

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
    ) -> TriageRiskEvaluationDTO:
        """Avalia risco clínico, gera hash do TCLE e valida SAMU 192 (RN04, RN07).

        Regras: docs/explanation/domains/triage-domain.md.
        História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
        """
        tcle_hash_final = _resolver_tcle_hash(tcle_texto, tcle_hash)
        sintomas_norm = normalizar_sintomas(sintomas)

        prioridade = classificar_risco_clinico(
            queixa_principal=queixa_principal,
            sintomas=sintomas_norm,
            escala_dor=escala_dor,
        )

        if prioridade == 1:
            resolved_atend_id = atendimento_id or uuid7()
            if self._notifier is not None:
                alerta = EmergencyAlertDTO(
                    atendimento_id=resolved_atend_id,
                    queixa_principal=queixa_principal,
                    sintomas_alerta=sintomas_norm,
                )
                await self._notifier.notificar_emergencia_samu(alerta)

            if raise_on_emergency:
                raise EmergenciaCriticaSamuError(
                    f"Emergência médica crítica detectada (Nível 1) para atendimento "
                    f"'{resolved_atend_id}' (queixa='{queixa_principal}'). "
                    "Ingresso no PA Virtual bloqueado. Acione imediatamente o SAMU 192."
                )

            return TriageRiskEvaluationDTO(
                prioridade_clinica=1,
                tcle_hash=tcle_hash_final,
                alerta_samu_disparado=True,
                instrucao_redirecionamento=INSTRUCAO_SAMU_PADRAO,
            )

        return TriageRiskEvaluationDTO(
            prioridade_clinica=prioridade,
            tcle_hash=tcle_hash_final,
            alerta_samu_disparado=False,
            instrucao_redirecionamento=None,
        )

    async def registrar_triagem(
        self,
        atendimento_id: UUID,
        queixa_principal: str,
        sintomas: Sequence[str],
        prioridade_calculada: int | None = None,
        alerta_samu_disparado: bool = False,
        escala_dor: int = 0,
    ) -> UUID:
        """Persiste atomicamente Triagem associada 1:1 ao atendimento (RN04, RN07).

        Regras: docs/explanation/domains/triage-domain.md.
        História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
        """
        if self._session is None:
            raise RuntimeError(
                "AsyncSession é necessária para persistir o registro de "
                f"Triagem do atendimento '{atendimento_id}'."
            )

        triagem = Triagem.criar_avaliada(
            atendimento_id=atendimento_id,
            queixa_principal=queixa_principal,
            sintomas=sintomas,
            escala_dor=escala_dor,
            alerta_samu_disparado=alerta_samu_disparado,
        )
        if (
            prioridade_calculada is not None
            and int(prioridade_calculada) != triagem.prioridade_calculada
        ):
            raise TriagemInvalidaError(
                f"Prioridade calculada '{prioridade_calculada}' incoerente com a "
                "queixa e sintomas informados; esperado "
                f"'{triagem.prioridade_calculada}'."
            )

        self._session.add(triagem)
        await self._session.flush()
        return triagem.id

    async def obter_queixas_por_atendimentos(
        self,
        atendimento_ids: Sequence[UUID],
    ) -> dict[UUID, str | None]:
        """Consulta queixas principais das triagens por atendimento via ORM (RF-01).

        Retorna mapa atendimento_id -> queixa_principal.
        Regras: docs/explanation/domains/triage-domain.md.
        """
        if not atendimento_ids:
            return {}
        if self._session is None:
            raise RuntimeError(
                "AsyncSession é necessária para consultar queixas de Triagem "
                f"para {len(atendimento_ids)} atendimento(s)."
            )

        ids_unicos = list(dict.fromkeys(atendimento_ids))
        stmt = select(Triagem).where(Triagem.atendimento_id.in_(ids_unicos))
        res = await self._session.execute(stmt)
        triagens = res.scalars().all()
        queixas: dict[UUID, str | None] = {
            triagem.atendimento_id: triagem.queixa_principal for triagem in triagens
        }
        return queixas
