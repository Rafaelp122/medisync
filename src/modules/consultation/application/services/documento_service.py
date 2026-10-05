"""Clinical document lifecycle service with canonical storage keys.

Owns emitir/compilar/assinar for DocumentoClinico using the canonical
``orgs/{org}/consultations/...`` key builder plus SignedCachePort.
"""

import contextlib
import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.errors import NotFoundError
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    EmitirDocumentoClinicoCommand,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    DocumentoItemPDFDTO,
    DocumentoPDFPayload,
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    DocumentoClinicoNaoEncontradoError,
    PrescricaoFisicaObrigatoriaError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    DocumentoItem,
    EvolucaoClinica,
    TipoDocumentoClinico,
)
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)
from src.modules.consultation.domain.s3_keys import build_signed_document_key

_PROHIBITED_DOC_TYPES = frozenset({"NOTIFICACAO_RECEITA_A", "NOTIFICACAO_RECEITA_B"})
_STATUS_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


class DocumentoService:
    """Application service owning clinical document emit/compile/sign."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_generator: PDFGeneratorPort,
        signer: ICPBrasilSignerPort,
        storage: StoragePort,
        cache: SignedCachePort,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._signer = signer
        self._storage = storage
        self._cache = cache

    @property
    def storage(self) -> StoragePort:
        """Return the injected storage port instance."""
        return self._storage

    @property
    def cache(self) -> SignedCachePort:
        """Return the injected signed-document cache."""
        return self._cache

    async def is_assinado(self, doc: DocumentoClinico) -> bool:
        """Check SignedCachePort only; key prefix matches unsigned docs too."""
        return await self._cache.is_assinado(doc.id)

    async def _verificar_atendimento_finalizado(self, atendimento_id: UUID) -> bool:
        """Check whether the underlying attendance reached terminal status in DB."""
        try:
            status_stmt = text("SELECT status FROM atendimentos WHERE id = :atend_id")
            res = await self._session.execute(status_stmt, {"atend_id": atendimento_id})
            val = res.scalar_one_or_none()
            if val is not None:
                return str(val).strip().upper() in _STATUS_TERMINAIS
        except Exception:
            return False
        return False

    async def emitir_documento(
        self, command: EmitirDocumentoClinicoCommand
    ) -> DocumentoClinico:
        """Issue clinical document with prescription items enforcing Portaria 344/98."""
        tipo_str = str(command.tipo_documento).strip().upper()
        if tipo_str in _PROHIBITED_DOC_TYPES:
            raise PrescricaoFisicaObrigatoriaError(
                f"O tipo de documento '{command.tipo_documento}' exige talonário "
                "físico impresso de segurança (Notificação de Receita Amarela/Azul) "
                "conforme a Portaria SVS/MS nº 344/98 e a Resolução CFM nº 2.314/2022. "
                "Sua emissão por telemedicina é expressamente vedada."
            )

        # Check if consultation is already finalized
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()
        is_term = await self._verificar_atendimento_finalizado(command.atendimento_id)

        if (evolucao is not None and evolucao.is_finalizado) or is_term:
            if evolucao is not None:
                evolucao.marcar_finalizado()
            raise ConsultaFinalizadaError(
                "Não é permitido emitir documentos clínicos de consulta finalizada."
            )

        # Pre-validate all items before persistence
        for item in command.itens:
            validar_substancia_permitida_telemedicina(item.medicamento)

        new_doc_id = uuid7()
        chave_s3 = (
            command.chave_s3.strip()
            if command.chave_s3 and command.chave_s3.strip()
            else build_signed_document_key(
                command.organizacao_id, command.atendimento_id, new_doc_id
            )
        )

        sha256_hash = (
            command.sha256_hash.strip().lower()
            if command.sha256_hash and command.sha256_hash.strip()
            else hashlib.sha256(
                f"{command.atendimento_id}:{chave_s3}:{datetime.now(UTC).isoformat()}".encode()
            ).hexdigest()
        )

        doc = DocumentoClinico(
            organizacao_id=command.organizacao_id,
            atendimento_id=command.atendimento_id,
            medico_id=command.medico_id,
            tipo_documento=tipo_str,
            chave_s3=chave_s3,
            sha256_hash=sha256_hash,
            id=new_doc_id,
        )
        self._session.add(doc)
        await self._session.flush()

        for item_dto in command.itens:
            is_c1 = (
                item_dto.controle_especial
                or doc.tipo_documento
                == TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1
            )
            item_entity = DocumentoItem(
                organizacao_id=command.organizacao_id,
                documento_id=doc.id,
                medicamento=item_dto.medicamento,
                dosagem=item_dto.dosagem,
                posologia=item_dto.posologia,
                duracao=item_dto.duracao,
                controle_especial=is_c1,
            )
            doc.adicionar_item(item_entity)
            self._session.add(item_entity)

        await self._session.flush()
        await self._session.commit()
        # Reload with itens eagerly (selectin) so Pydantic model_validate
        # stays sync-safe; expire_on_commit=False keeps columns, no refresh.
        reload_stmt = (
            select(DocumentoClinico)
            .where(DocumentoClinico.id == doc.id)
            .options(selectinload(DocumentoClinico.itens))
        )
        reload_res = await self._session.execute(reload_stmt)
        reloaded = reload_res.scalar_one()
        return reloaded

    async def compilar_pdf(self, documento_id: UUID) -> bytes:
        """Compile PDF/A binary with ITI verification QR Code."""
        stmt = (
            select(DocumentoClinico)
            .where(DocumentoClinico.id == documento_id)
            .options(selectinload(DocumentoClinico.itens))
        )
        res = await self._session.execute(stmt)
        doc = res.scalar_one_or_none()
        if doc is None:
            raise DocumentoClinicoNaoEncontradoError(
                f"Documento clínico '{documento_id}' não encontrado."
            )

        if doc.chave_s3:
            with contextlib.suppress(Exception):
                return await self._storage.obter_documento(doc.chave_s3)

        org_nome = "MediSync Pronto-Atendimento Virtual"
        org_cnpj: str | None = None
        org_cnes: str | None = None
        org_end: str | None = None
        org_tel: str | None = None

        with contextlib.suppress(Exception):
            async with self._session.begin_nested():
                org_res = await self._session.execute(
                    text(
                        "SELECT razao_social, nome_fantasia, cnpj "
                        "FROM organizacoes WHERE id = :org_id"
                    ),
                    {"org_id": doc.organizacao_id},
                )
                org_row = org_res.mappings().first()
                if org_row:
                    org_nome = str(
                        org_row.get("nome_fantasia")
                        or org_row.get("razao_social")
                        or org_nome
                    )
                    org_cnpj = str(org_row.get("cnpj")) if org_row.get("cnpj") else None

        medico_nome = "Médico Assistente"
        medico_crm = "00000"
        medico_crm_uf = "BR"
        medico_rqe: str | None = None

        with contextlib.suppress(Exception):
            async with self._session.begin_nested():
                med_res = await self._session.execute(
                    text(
                        "SELECT nome_completo, crm, crm_uf "
                        "FROM profissionais WHERE id = :med_id"
                    ),
                    {"med_id": doc.medico_id},
                )
                med_row = med_res.mappings().first()
                if med_row:
                    medico_nome = str(med_row.get("nome_completo") or medico_nome)
                    medico_crm = str(med_row.get("crm") or medico_crm)
                    medico_crm_uf = str(med_row.get("crm_uf") or medico_crm_uf)

        paciente_nome = "Paciente"
        paciente_cpf = "000.000.000-00"
        paciente_nasc: str | None = None
        paciente_end: str | None = None

        with contextlib.suppress(Exception):
            async with self._session.begin_nested():
                pac_res = await self._session.execute(
                    text(
                        "SELECT p.nome_completo, p.cpf, p.data_nascimento, "
                        "p.logradouro, p.numero, p.bairro, p.cidade, p.estado "
                        "FROM atendimentos a "
                        "JOIN pacientes p ON a.paciente_id = p.id "
                        "WHERE a.id = :atend_id"
                    ),
                    {"atend_id": doc.atendimento_id},
                )
                pac_row = pac_res.mappings().first()
                if pac_row:
                    paciente_nome = str(pac_row.get("nome_completo") or paciente_nome)
                    paciente_cpf = str(pac_row.get("cpf") or paciente_cpf)
                    data_n = pac_row.get("data_nascimento")
                    if data_n is not None:
                        paciente_nasc = (
                            data_n.strftime("%d/%m/%Y")  # pyright: ignore[reportAttributeAccessIssue]
                            if hasattr(data_n, "strftime")
                            else str(data_n)
                        )
                    end_parts = [
                        str(pac_row.get("logradouro") or "").strip(),
                        str(pac_row.get("numero") or "").strip(),
                        str(pac_row.get("bairro") or "").strip(),
                        str(pac_row.get("cidade") or "").strip(),
                        str(pac_row.get("estado") or "").strip(),
                    ]
                    valid_parts = [p for p in end_parts if p]
                    if valid_parts:
                        paciente_end = ", ".join(valid_parts)

        cid10: str | None = None
        with contextlib.suppress(Exception):
            async with self._session.begin_nested():
                ev_res = await self._session.execute(
                    text(
                        "SELECT cid10_principal FROM evolucoes_clinicas "
                        "WHERE atendimento_id = :atend_id"
                    ),
                    {"atend_id": doc.atendimento_id},
                )
                cid10_val = ev_res.scalar_one_or_none()
                if cid10_val:
                    cid10 = str(cid10_val)

        itens_pdf = [
            DocumentoItemPDFDTO(
                medicamento=it.medicamento,
                dosagem=it.dosagem,
                posologia=it.posologia,
                duracao=it.duracao,
                controle_especial=it.controle_especial,
            )
            for it in doc.itens
        ]

        payload = DocumentoPDFPayload(
            documento_id=doc.id,
            tipo_documento=doc.tipo_documento,
            data_emissao=doc.assinado_em,
            organizacao_nome=org_nome,
            organizacao_cnpj=org_cnpj,
            organizacao_cnes=org_cnes,
            organizacao_endereco=org_end,
            organizacao_telefone=org_tel,
            medico_nome=medico_nome,
            medico_crm=medico_crm,
            medico_crm_uf=medico_crm_uf,
            medico_rqe=medico_rqe,
            paciente_nome=paciente_nome,
            paciente_cpf=paciente_cpf,
            paciente_data_nascimento=paciente_nasc,
            paciente_endereco=paciente_end,
            itens=itens_pdf,
            cid10=cid10,
            sha256_hash=doc.sha256_hash,
        )

        return self._pdf_generator.gerar_pdf(payload)

    async def assinar(
        self,
        documento_id: UUID,
        atendimento_id: UUID,
        credenciais: DoctorCertificateCredentials,
    ) -> tuple[DocumentoClinico, bytes]:
        """Sign clinical document with ICP-Brasil PAdES standard via Cloud PSC."""
        stmt = (
            select(DocumentoClinico)
            .where(DocumentoClinico.id == documento_id)
            .options(selectinload(DocumentoClinico.itens))
        )
        res = await self._session.execute(stmt)
        doc = res.scalar_one_or_none()
        if doc is None:
            raise NotFoundError(f"Documento clínico '{documento_id}' não encontrado.")

        if doc.atendimento_id != atendimento_id:
            raise NotFoundError(
                f"Documento '{documento_id}' não pertence ao "
                f"atendimento '{atendimento_id}'."
            )

        is_term = await self._verificar_atendimento_finalizado(doc.atendimento_id)
        if doc.is_finalizado or is_term:
            raise ConsultaFinalizadaError(
                "Não é permitido alterar ou assinar documento de "
                "consulta já finalizada."
            )

        pdf_bytes = await self.compilar_pdf(documento_id)
        signed_bytes = await self._signer.assinar_pdf(pdf_bytes, credenciais)

        new_hash = hashlib.sha256(signed_bytes).hexdigest()
        doc.sha256_hash = new_hash
        doc.assinado_em = datetime.now(UTC)

        s3_key = build_signed_document_key(
            doc.organizacao_id, doc.atendimento_id, doc.id
        )
        await self._storage.salvar_documento(s3_key, signed_bytes)
        doc.chave_s3 = s3_key
        await self._cache.marcar_assinado(doc.id)
        await self._session.flush()
        await self._session.commit()

        return doc, signed_bytes
