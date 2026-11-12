"""Ambulatory production service for SUS BPA-I and SISAB consolidation (ADR-012)."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import AuditTrailPort
from src.modules.ambulatory.application.dtos import (
    BpaArquivoExportadoDTO,
    BpaProducaoDTO,
    BpaRegistroDetalheDTO,
    ConsolidarTeleconsultaCommand,
    ListaProducaoAmbulatorialDTO,
)
from src.modules.ambulatory.application.ports.bpa_directory_port import BpaDirectoryPort
from src.modules.ambulatory.domain.bpa_formatter import (
    BpaHeaderData,
    BpaItemData,
    BpaPositionalFormatter,
    validar_competencia,
)
from src.modules.ambulatory.domain.exceptions import ProducaoNaoEncontradaError
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)


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

    @staticmethod
    def converter_para_bpa_dto(producao: ProducaoAmbulatorial) -> BpaProducaoDTO:
        """Converte a entidade de produção ambulatorial para o DTO BPA-I.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md e
        docs/explanation/domains/ambulatory-domain.md.
        """
        return BpaProducaoDTO(
            atendimento_id=producao.atendimento_id,
            cnes=producao.cnes,
            codigo_sigtap=producao.codigo_sigtap,
            carater_atendimento=producao.carater_atendimento,
            consolidado_em=producao.consolidado_em,
        )

    async def consolidar_teleconsulta(
        self,
        cmd: ConsolidarTeleconsultaCommand,
        *,
        organizacao_id: int,
    ) -> BpaProducaoDTO:
        """Consolida atendimento médico finalizado para faturamento BPA-I no SUS.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md e
        docs/explanation/domains/ambulatory-domain.md.
        Garante idempotência caso o atendimento já tenha sido consolidado.
        """
        # 1. Checagem de idempotência
        stmt = select(ProducaoAmbulatorial).where(
            ProducaoAmbulatorial.atendimento_id == cmd.atendimento_id
        )
        result = await self._session.execute(stmt)
        existente = result.scalar_one_or_none()
        if existente is not None:
            return self.converter_para_bpa_dto(existente)

        # 2. Criação da produção ambulatorial
        producao = ProducaoAmbulatorial(
            organizacao_id=organizacao_id,
            atendimento_id=cmd.atendimento_id,
            profissional_id=cmd.profissional_id,
            paciente_id=cmd.paciente_id,
            cnes=cmd.cnes,
            codigo_sigtap=cmd.codigo_sigtap,
            carater_atendimento=cmd.carater_atendimento,
        )
        self._session.add(producao)
        await self._session.flush()

        if self._audit_trail is not None:
            # Validação de consistência cadastral (US-11 Cenário 2)
            cns_ou_cpf = (cmd.paciente_cns or "").strip() or (
                cmd.paciente_cpf or ""
            ).strip()
            tem_identificacao = bool(cns_ou_cpf and len(cns_ou_cpf) >= 11)
            tem_nascimento = bool((cmd.paciente_data_nascimento or "").strip())
            if (cmd.paciente_cns is not None or cmd.paciente_cpf is not None) and (
                not tem_identificacao or not tem_nascimento
            ):
                await self._audit_trail.record_event(
                    organizacao_id=organizacao_id,
                    tipo_evento="PRODUCAO_PENDENCIA_CADASTRAL",
                    ator_tipo="SISTEMA",
                    ator_papel="WORKER",
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
                organizacao_id=organizacao_id,
                tipo_evento="PRODUCAO_AMBULATORIAL_CONSOLIDADA",
                ator_tipo="SISTEMA",
                ator_papel="WORKER",
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

        await self._session.commit()

        return self.converter_para_bpa_dto(producao)

    async def listar_producao_por_competencia(
        self,
        *,
        organizacao_id: int,
        competencia: str,
        page: int = 1,
        size: int = 50,
    ) -> ListaProducaoAmbulatorialDTO:
        """Lista registros de produção ambulatorial consolidada por competência.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md e
        docs/explanation/domains/ambulatory-domain.md.
        """
        comp_validada = validar_competencia(competencia)

        count_stmt = (
            select(func.count())
            .select_from(ProducaoAmbulatorial)
            .where(
                ProducaoAmbulatorial.organizacao_id == organizacao_id,
                ProducaoAmbulatorial.competencia == comp_validada,
            )
        )
        total_res = await self._session.execute(count_stmt)
        total = total_res.scalar_one_or_none() or 0

        offset = max(page - 1, 0) * size
        stmt = (
            select(ProducaoAmbulatorial)
            .where(
                ProducaoAmbulatorial.organizacao_id == organizacao_id,
                ProducaoAmbulatorial.competencia == comp_validada,
            )
            .order_by(ProducaoAmbulatorial.consolidado_em.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self._session.execute(stmt)
        producoes = res.scalars().all()

        items = [self.converter_para_bpa_dto(p) for p in producoes]
        return ListaProducaoAmbulatorialDTO(
            items=items,
            total=total,
            competencia=comp_validada,
            organizacao_id=organizacao_id,
            page=page,
            size=size,
        )

    async def gerar_arquivo_bpa_i(
        self,
        *,
        organizacao_id: int,
        competencia: str,
    ) -> BpaArquivoExportadoDTO:
        """Gera o arquivo magnético posicional BPA-I para exportação ao SIA-SUS/DATASUS.

        Regras: docs/user-stories/US-11-liquidacao-fechamento-contabil.md e
        docs/explanation/domains/ambulatory-domain.md.
        """
        comp_validada = validar_competencia(competencia)

        if self._bpa_directory is None:
            raise RuntimeError(
                "BpaDirectoryPort não configurado no serviço de produção ambulatorial."
            )

        registros = await self._bpa_directory.buscar_detalhes_bpa_lote(
            organizacao_id=organizacao_id,
            competencia=comp_validada,
        )

        if not registros:
            raise ProducaoNaoEncontradaError(
                competencia=comp_validada,
                organizacao_id=organizacao_id,
            )

        # Auditoria de pendência cadastral em lote (US-11 Cenário 2)
        await self._auditar_pendencias_cadastrais_lote(
            organizacao_id=organizacao_id,
            registros=registros,
        )

        primeiro = registros[0]
        header = BpaHeaderData(
            competencia=comp_validada,
            total_linhas=len(registros),
            total_folhas=(len(registros) + 19) // 20,
            smt_vrf=0,
            org_nome=primeiro.org_nome,
            org_sigla=primeiro.org_sigla,
            cnpj=primeiro.org_cnpj,
            destino="SECRETARIA MUNICIPAL DE SAUDE",
            destino_tipo="M",
            versao="03.01",
        )

        itens_formatados = [
            BpaItemData(
                cnes=r.cnes,
                competencia=comp_validada,
                cns_medico=r.medico_cns,
                cbo=r.medico_cbo,
                data_atendimento=r.consolidado_em.strftime("%Y%m%d"),
                num_folha=0,
                num_seq=0,
                codigo_sigtap=r.codigo_sigtap,
                cns_paciente=r.paciente_cns,
                sexo=r.paciente_sexo,
                ibge_municipio=r.paciente_ibge,
                cid=r.cid,
                idade=r.idade,
                carater_atendimento=r.carater_atendimento,
                paciente_nome=r.paciente_nome,
                data_nascimento=r.paciente_data_nascimento,
            )
            for r in registros
        ]

        linhas = BpaPositionalFormatter.gerar_arquivo_bpa(header, itens_formatados)
        conteudo = "\r\n".join(linhas) + "\r\n"
        cnes_arquivo = primeiro.cnes or "0000000"
        nome_arquivo = f"BPA_I_{comp_validada}_{cnes_arquivo}.txt"

        return BpaArquivoExportadoDTO(
            conteudo=conteudo,
            nome_arquivo=nome_arquivo,
            total_registros=len(registros),
            total_folhas=(len(registros) + 19) // 20,
            competencia=comp_validada,
        )

    async def _auditar_pendencias_cadastrais_lote(
        self,
        *,
        organizacao_id: int,
        registros: Sequence[BpaRegistroDetalheDTO],
    ) -> None:
        """Registra auditoria para itens de lote com cadastro incompleto."""
        if self._audit_trail is None:
            return

        for r in registros:
            cns_limpo = r.paciente_cns.replace("0", "").strip()
            cpf_limpo = (r.paciente_cpf or "").strip()
            dt_nasc = r.paciente_data_nascimento.strip()
            invalido = (
                (not cns_limpo and not cpf_limpo)
                or not dt_nasc
                or dt_nasc == "20000101"
            )
            if invalido:
                await self._audit_trail.record_event(
                    organizacao_id=organizacao_id,
                    tipo_evento="PRODUCAO_PENDENCIA_CADASTRAL",
                    ator_tipo="SISTEMA",
                    ator_papel="WORKER",
                    ator_id=None,
                    atendimento_id=r.atendimento_id,
                    estado_anterior=None,
                    novo_estado="PENDENCIA_CADASTRAL",
                    payload={
                        "producao_id": str(r.producao_id),
                        "atendimento_id": str(r.atendimento_id),
                        "paciente_id": str(r.paciente_id),
                        "motivo": "Cadastro incompleto: CNS/CPF ou nascimento",
                    },
                )
