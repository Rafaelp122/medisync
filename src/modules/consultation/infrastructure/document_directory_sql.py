"""SQL directory adapter for public verification (isolated raw SQL, infra only)."""

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
    DocumentDirectoryPort,
)
from src.modules.consultation.domain.exceptions import DocumentoIntegridadeError

logger = logging.getLogger("medisync.validation")

_ORG_DEFAULT = "MediSync Pronto-Atendimento Virtual"


class SqlDocumentDirectory(DocumentDirectoryPort):
    """Raw-SQL directory adapter (sole place allowed to query identity tables).

    Location decision: lives in consultation infra (not identity) to avoid
    cross-module model imports (tach). Uses only SQL text(), never identity
    models, preserving module independence. Chosen over neutral provider
    because queries are consultation-specific (atendimento->paciente join).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_dados_verificacao(
        self,
        organizacao_id: int,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> DadosVerificacaoDirectory:
        org_res = await self._session.execute(
            text(
                "SELECT razao_social, nome_fantasia FROM organizacoes "
                "WHERE id = :org_id"
            ),
            {"org_id": organizacao_id},
        )
        org_row = org_res.mappings().first()
        org_nome = _ORG_DEFAULT
        if org_row:
            org_nome = str(
                org_row.get("nome_fantasia")
                or org_row.get("razao_social")
                or _ORG_DEFAULT
            )

        med_res = await self._session.execute(
            text(
                "SELECT nome_completo, crm, crm_uf FROM profissionais "
                "WHERE id = :med_id"
            ),
            {"med_id": medico_id},
        )
        med_row = med_res.mappings().first()
        if med_row is None or not med_row.get("nome_completo"):
            logger.error(
                "Integridade: médico %s ausente para verificação pública",
                medico_id,
            )
            raise DocumentoIntegridadeError(
                "Dados do médico emissor ausentes para o documento."
            )
        medico_nome = str(med_row.get("nome_completo"))
        medico_crm = str(med_row.get("crm") or "")
        medico_uf = str(med_row.get("crm_uf") or "")
        if not medico_crm or not medico_uf:
            logger.error("Integridade: CRM/UF ausente para médico %s", medico_id)
            raise DocumentoIntegridadeError(
                "Dados do médico emissor incompletos para o documento."
            )

        pac_res = await self._session.execute(
            text(
                "SELECT p.nome_completo, p.cpf FROM atendimentos a "
                "JOIN pacientes p ON a.paciente_id = p.id "
                "WHERE a.id = :atend_id"
            ),
            {"atend_id": atendimento_id},
        )
        pac_row = pac_res.mappings().first()
        if pac_row is None or not pac_row.get("nome_completo"):
            logger.error(
                "Integridade: paciente ausente para atendimento %s",
                atendimento_id,
            )
            raise DocumentoIntegridadeError(
                "Dados do paciente ausentes para o documento."
            )

        return DadosVerificacaoDirectory(
            organizacao_nome=org_nome,
            medico_nome=medico_nome,
            medico_crm=medico_crm,
            medico_crm_uf=medico_uf,
            paciente_nome=str(pac_row.get("nome_completo") or ""),
            paciente_cpf=str(pac_row.get("cpf") or ""),
        )
