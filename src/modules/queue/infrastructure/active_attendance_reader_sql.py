"""SQL adapter for resolving active patient attendance across modules."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.queue.domain.enums import TERMINAL_STATUSES
from src.modules.queue.domain.models.atendimento import Atendimento

_TERMINAL_STATUS_VALUES = tuple(str(s) for s in TERMINAL_STATUSES)


class SqlActiveAttendanceReader:
    """Leitor SQL de atendimento ativo do paciente para reidratação de sessão.

    Regras: RF-01, ADR-001 e docs/user-stories/US-02-autenticacao-passwordless-otp.md.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_atendimento_ativo_paciente(
        self,
        organizacao_id: int,
        paciente_id: UUID,
    ) -> UUID | None:
        """Retorna o ID do atendimento ativo mais recente do paciente na organização.

        Regras: RF-01, US-02 (§2 Cenário 5) e
        docs/user-stories/US-14-biometria-passkeys-webauthn.md.
        """
        stmt = (
            select(Atendimento.id)
            .where(
                Atendimento.organizacao_id == organizacao_id,
                Atendimento.paciente_id == paciente_id,
                Atendimento.status.notin_(_TERMINAL_STATUS_VALUES),
            )
            .order_by(Atendimento.data_entrada_fila.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
