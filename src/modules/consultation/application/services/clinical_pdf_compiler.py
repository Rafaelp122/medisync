"""Shared clinical PDF/A compiler enforcing ownership and directory integrity."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
    DocumentDirectoryPort,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    DocumentoItemPDFDTO,
    DocumentoPDFPayload,
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.domain.exceptions import (
    DocumentoClinicoNaoEncontradoError,
    DocumentoIntegridadeError,
    DocumentoNaoEncontradoNoStorageError,
)
from src.modules.consultation.domain.models import DocumentoClinico, EvolucaoClinica


def _validar_dados_diretorio(
    dados: DadosVerificacaoDirectory,
    documento_id: UUID,
) -> None:
    """Garante integridade de metadados médicos e cadastrais sem placeholders.

    Regras: CFM nº 2.314/2022 e
    docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
    """
    campos_obrigatorios = {
        "organizacao_nome": dados.organizacao_nome,
        "medico_nome": dados.medico_nome,
        "medico_crm": dados.medico_crm,
        "medico_crm_uf": dados.medico_crm_uf,
        "paciente_nome": dados.paciente_nome,
        "paciente_cpf": dados.paciente_cpf,
    }
    ausentes = [
        campo
        for campo, valor in campos_obrigatorios.items()
        if not valor or not str(valor).strip()
    ]
    if ausentes:
        raise DocumentoIntegridadeError(
            f"Dados cadastrais incompletos para o documento '{documento_id}': "
            f"campos ausentes {ausentes}."
        )


class ClinicalPdfCompiler:
    """Compiles archival PDF/A documents enforcing strict attendance ownership."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_generator: PDFGeneratorPort,
        storage: StoragePort,
        directory: DocumentDirectoryPort | None = None,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._storage = storage
        self._directory = directory

    async def _buscar_documento(
        self,
        documento_id: UUID,
        atendimento_id: UUID | None,
    ) -> DocumentoClinico:
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
        if atendimento_id is not None and doc.atendimento_id != atendimento_id:
            raise DocumentoClinicoNaoEncontradoError(
                f"Documento clínico '{documento_id}' não pertence ao "
                f"atendimento '{atendimento_id}'."
            )
        return doc

    async def _obter_cid10_atendimento(self, atendimento_id: UUID) -> str | None:
        ev_stmt = select(EvolucaoClinica.cid10_principal).where(
            EvolucaoClinica.atendimento_id == atendimento_id
        )
        ev_res = await self._session.execute(ev_stmt)
        cid10_val = ev_res.scalar_one_or_none()
        return str(cid10_val) if cid10_val else None

    async def compilar(
        self,
        documento_id: UUID,
        *,
        atendimento_id: UUID | None = None,
    ) -> bytes:
        """Compila binário PDF/A-1b validando posse do atendimento e integridade.

        Impede IDOR horizontal entre atendimentos e veda placeholders fictícios.
        Regras: CFM nº 2.314/2022, LGPD Art. 11/16 e
        docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        doc = await self._buscar_documento(documento_id, atendimento_id)

        if doc.chave_s3:
            try:
                return await self._storage.obter_documento(doc.chave_s3)
            except DocumentoNaoEncontradoNoStorageError:
                pass

        if self._directory is None:
            raise DocumentoIntegridadeError(
                f"Diretório clínico ausente para compilar documento '{documento_id}'."
            )

        dir_data = await self._directory.obter_dados_verificacao(
            medico_id=doc.medico_id,
            atendimento_id=doc.atendimento_id,
        )
        _validar_dados_diretorio(dir_data, documento_id)

        cid10 = await self._obter_cid10_atendimento(doc.atendimento_id)
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
            data_emissao=doc.assinado_em or datetime.now(UTC),
            organizacao_nome=dir_data.organizacao_nome,
            organizacao_cnpj=dir_data.organizacao_cnpj,
            organizacao_cnes=dir_data.cnes,
            medico_nome=dir_data.medico_nome,
            medico_crm=dir_data.medico_crm,
            medico_crm_uf=dir_data.medico_crm_uf,
            paciente_nome=dir_data.paciente_nome,
            paciente_cpf=dir_data.paciente_cpf,
            paciente_data_nascimento=dir_data.paciente_data_nascimento,
            paciente_endereco=dir_data.paciente_endereco,
            itens=itens_pdf,
            cid10=cid10,
            sha256_hash=doc.sha256_hash,
        )

        return await asyncio.to_thread(self._pdf_generator.gerar_pdf, payload)
