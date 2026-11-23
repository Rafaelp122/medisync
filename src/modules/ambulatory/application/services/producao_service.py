"""Ambulatory production service for SUS BPA-I and SISAB consolidation (ADR-012)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.modules.ambulatory.application.dtos import (
    BpaArquivoExportadoDTO,
    ConsolidarTeleconsultaCommand,
)
from src.modules.ambulatory.application.ports.bpa_directory_port import BpaDirectoryPort
from src.modules.ambulatory.domain.bpa_formatter import (
    BpaPositionalFormatter,
    validar_competencia,
)
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)


def _is_unique_violation(exc: IntegrityError) -> bool:
    """Detect PostgreSQL unique constraint violation (SQLSTATE 23505)."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "23505":
        return True
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    return constraint == "uq_producoes_ambulatoriais_atendimento_id"


class ProducaoAmbulatorialService:
    """Serviço de aplicação para consolidação de produção ambulatorial SUS.

    Orquestra a persistência e exportação de itens de faturamento público
    (BPA-I / SISAB) vinculados ao procedimento SIGTAP 03.01.01.025-0.
    Regras: docs/explanation/domains/ambulatory-domain.md, US-11 e ADR-012.
    """

    def __init__(
        self,
        session: AsyncSession,
        audit_trail: AuditTrailPort | None = None,
        bpa_directory: BpaDirectoryPort | None = None,
    ) -> None:
        """Inicializa serviço com sessão assíncrona do SQLAlchemy e portas."""
        self._session = session
        self._audit_trail = audit_trail
        self._bpa_directory = bpa_directory

    async def _buscar_por_atendimento(
        self,
        atendimento_id: UUID,
    ) -> ProducaoAmbulatorial | None:
        stmt = select(ProducaoAmbulatorial).where(
            ProducaoAmbulatorial.atendimento_id == atendimento_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _tratar_conflito_insercao(
        self,
        exc: IntegrityError,
        atendimento_id: UUID,
        *,
        auto_commit: bool,
    ) -> ProducaoAmbulatorial:
        if auto_commit:
            await self._session.rollback()
        if not _is_unique_violation(exc):
            raise exc
        existente = await self._buscar_por_atendimento(atendimento_id)
        if existente is None:
            raise exc
        return existente

    async def _inserir_producao_idempotente(
        self,
        producao: ProducaoAmbulatorial,
        *,
        auto_commit: bool,
    ) -> tuple[ProducaoAmbulatorial, bool]:
        try:
            async with self._session.begin_nested():
                self._session.add(producao)
                await self._session.flush()
            return producao, True
        except IntegrityError as exc:
            existente = await self._tratar_conflito_insercao(
                exc,
                producao.atendimento_id,
                auto_commit=auto_commit,
            )
            return existente, False

    async def _registrar_auditoria_consolidacao(
        self,
        cmd: ConsolidarTeleconsultaCommand,
        producao: ProducaoAmbulatorial,
    ) -> None:
        if self._audit_trail is None:
            return

        cns_ou_cpf = (cmd.paciente_cns or "").strip() or (
            cmd.paciente_cpf or ""
        ).strip()
        tem_identificacao = bool(cns_ou_cpf and len(cns_ou_cpf) >= 11)
        tem_nascimento = bool((cmd.paciente_data_nascimento or "").strip())
        if (cmd.paciente_cns is not None or cmd.paciente_cpf is not None) and (
            not tem_identificacao or not tem_nascimento
        ):
            await self._audit_trail.record_event(
                tipo_evento="PRODUCAO_PENDENCIA_CADASTRAL",
                ator_tipo=AtorTipo.SISTEMA,
                ator_papel=AtorPapel.WORKER_ARQ,
                ator_id=None,
                atendimento_id=cmd.atendimento_id,
                estado_anterior=None,
                novo_estado="PENDENCIA_CADASTRAL",
                payload={
                    "atendimento_id": str(cmd.atendimento_id),
                    "paciente_id": str(cmd.paciente_id),
                    "motivo": "Cadastro incompleto: CNS/CPF ou nascimento",
                },
            )

        await self._audit_trail.record_event(
            tipo_evento="PRODUCAO_AMBULATORIAL_CONSOLIDADA",
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.WORKER_ARQ,
            ator_id=None,
            atendimento_id=cmd.atendimento_id,
            estado_anterior=None,
            novo_estado="CONSOLIDADO",
            payload={
                "producao_id": str(producao.id),
                "cnes": producao.cnes,
                "codigo_sigtap": producao.codigo_sigtap,
                "competencia": producao.competencia,
            },
        )

    async def consolidar_teleconsulta(
        self,
        cmd: ConsolidarTeleconsultaCommand,
        *,
        auto_commit: bool = True,
    ) -> ProducaoAmbulatorial:
        """Consolida atendimento médico finalizado para faturamento BPA-I no SUS.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md,
        docs/explanation/domains/ambulatory-domain.md, ADR-001 §6 e ADR-013.
        Garante idempotência sob concorrência (savepoint/rollback + releitura em 23505)
        e suporta execução flush-only (auto_commit=False) em transação compartilhada.
        """
        existente = await self._buscar_por_atendimento(cmd.atendimento_id)
        if existente is not None:
            return existente

        producao = ProducaoAmbulatorial(
            atendimento_id=cmd.atendimento_id,
            profissional_id=cmd.profissional_id,
            paciente_id=cmd.paciente_id,
            cnes=cmd.cnes,
            codigo_sigtap=cmd.codigo_sigtap,
            carater_atendimento=cmd.carater_atendimento,
        )
        persistida, criada_agora = await self._inserir_producao_idempotente(
            producao,
            auto_commit=auto_commit,
        )
        if not criada_agora:
            return persistida

        await self._registrar_auditoria_consolidacao(cmd, persistida)
        if auto_commit:
            await self._session.commit()

        return persistida

    async def listar_producao_por_competencia(
        self,
        *,
        competencia: str,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ProducaoAmbulatorial], int]:
        """Lista registros de produção ambulatorial consolidada por competência.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md,
        docs/explanation/domains/ambulatory-domain.md e ADR-013.
        """
        comp_validada = validar_competencia(competencia)

        count_stmt = (
            select(func.count())
            .select_from(ProducaoAmbulatorial)
            .where(ProducaoAmbulatorial.competencia == comp_validada)
        )
        total_res = await self._session.execute(count_stmt)
        total = total_res.scalar_one_or_none() or 0

        offset = max(page - 1, 0) * size
        stmt = (
            select(ProducaoAmbulatorial)
            .where(ProducaoAmbulatorial.competencia == comp_validada)
            .order_by(ProducaoAmbulatorial.consolidado_em.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self._session.execute(stmt)
        producoes = list(res.scalars().all())
        return producoes, total

    async def gerar_arquivo_bpa_i(
        self,
        *,
        competencia: str,
        destino: str = "SECRETARIA MUNICIPAL DE SAUDE",
        destino_tipo: str = "M",
    ) -> BpaArquivoExportadoDTO:
        """Gera o arquivo magnético posicional BPA-I em modo puramente read-only.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md,
        docs/explanation/domains/ambulatory-domain.md e ADR-013.
        """
        comp_validada = validar_competencia(competencia)

        if self._bpa_directory is None:
            raise RuntimeError(
                "BpaDirectoryPort não configurado no serviço de produção ambulatorial "
                f"(competência solicitada: '{comp_validada}')."
            )

        registros = await self._bpa_directory.buscar_detalhes_bpa_lote(
            competencia=comp_validada,
        )

        return BpaPositionalFormatter.compilar_remessa(
            comp_validada,
            registros,
            destino=destino,
            destino_tipo=destino_tipo,
        )
