"""Public document validation service without router SQL or fabricated data."""

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.errors import NotFoundError
from src.core.privacy import mascarar_cpf, mascarar_nome
from src.modules.consultation.application.dtos import (
    DocumentoValidacaoResult,
    DownloadResult,
    ItemValidacaoDTO,
)
from src.modules.consultation.application.ports.document_directory_port import (
    DocumentDirectoryPort,
)
from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.domain.exceptions import (
    DocumentoNaoEncontradoNoStorageError,
)
from src.modules.consultation.domain.models import DocumentoClinico
from src.modules.consultation.domain.s3_keys import (
    build_signed_document_key,
    is_signed_document_key,
)

logger = logging.getLogger("medisync.validation")

_MSG_VALIDACAO_INVALIDA = "Token de validação inválido ou documento não encontrado."
_MSG_DOC_AUSENTE = "Documento clínico não encontrado ou token inválido."


class DocumentValidationService:
    """Application service for public QR validation and presigned download."""

    def __init__(
        self,
        session: AsyncSession,
        directory: DocumentDirectoryPort,
        storage: StoragePort,
        compilador_pdf: Callable[[UUID], Awaitable[bytes]],
        cache: SignedCachePort | None = None,
    ) -> None:
        self._session = session
        self._directory = directory
        self._storage = storage
        self._compilador_pdf = compilador_pdf
        self._cache = cache

    @staticmethod
    def parse_token(token_validacao: str) -> UUID:
        """Parse validation token or raise 404 NotFoundError."""
        try:
            return UUID(token_validacao.strip())
        except (ValueError, AttributeError) as err:
            raise NotFoundError(_MSG_VALIDACAO_INVALIDA) from err

    async def _is_assinado(self, doc: DocumentoClinico) -> bool:
        if self._cache is not None and await self._cache.is_assinado(doc.id):
            return True
        return is_signed_document_key(doc.chave_s3, doc.organizacao_id)

    @staticmethod
    def build_s3_key(organizacao_id: int, atendimento_id: UUID, doc_id: UUID) -> str:
        """Canonical signed-document S3 key (single source of truth)."""
        return build_signed_document_key(organizacao_id, atendimento_id, doc_id)

    async def _carregar_documento(self, doc_id: UUID) -> DocumentoClinico:
        stmt = (
            select(DocumentoClinico)
            .where(DocumentoClinico.id == doc_id)
            .options(selectinload(DocumentoClinico.itens))
        )
        res = await self._session.execute(stmt)
        doc = res.scalar_one_or_none()
        if doc is None:
            raise NotFoundError(_MSG_DOC_AUSENTE)
        return doc

    async def validar_documento(self, token: str) -> DocumentoValidacaoResult:
        """Validate authenticity and return LGPD-masked verification snapshot."""
        doc_id = self.parse_token(token)
        doc = await self._carregar_documento(doc_id)

        dados = await self._directory.obter_dados_verificacao(
            doc.organizacao_id, doc.medico_id, doc.atendimento_id
        )

        is_assinado = await self._is_assinado(doc)
        status_doc = "ASSINADO" if is_assinado else "EMITIDO"
        itens = [
            ItemValidacaoDTO(
                medicamento=it.medicamento,
                dosagem=it.dosagem,
                posologia=it.posologia,
                duracao=it.duracao,
                controle_especial=it.controle_especial,
            )
            for it in doc.itens
        ]
        return DocumentoValidacaoResult(
            documento_id=doc.id,
            tipo_documento=str(doc.tipo_documento),
            status_documento=status_doc,
            sha256_hash=doc.sha256_hash,
            assinado_em=doc.assinado_em if is_assinado else None,
            emissor_medico_nome=dados.medico_nome,
            emissor_medico_crm=dados.medico_crm,
            emissor_medico_uf=dados.medico_crm_uf,
            organizacao_nome=dados.organizacao_nome,
            paciente_nome_mascarado=mascarar_nome(dados.paciente_nome),
            paciente_cpf_mascarado=mascarar_cpf(dados.paciente_cpf),
            assinatura_digital_valida=is_assinado,
            conformidade_icp_brasil=is_assinado,
            itens=itens,
        )

    async def _garantir_documento_no_storage(
        self, doc: DocumentoClinico, s3_key: str
    ) -> None:
        """Ensure binary exists in storage, compiling on demand without suppress."""
        try:
            await self._storage.obter_documento(s3_key)
            return
        except DocumentoNaoEncontradoNoStorageError:
            logger.info(
                "Documento %s ausente no storage, compilando sob demanda",
                doc.id,
            )
        except Exception as exc:
            logger.exception(
                "Falha inesperada ao ler storage para documento %s: %s",
                doc.id,
                exc,
            )
            raise DocumentoNaoEncontradoNoStorageError(
                "Arquivo do documento não disponível para download no storage."
            ) from exc

        try:
            pdf_bytes = await self._compilador_pdf(doc.id)
            await self._storage.salvar_documento(s3_key, pdf_bytes)
        except DocumentoNaoEncontradoNoStorageError:
            raise
        except Exception as exc:
            logger.exception(
                "Falha ao compilar/persistir documento %s: %s", doc.id, exc
            )
            raise DocumentoNaoEncontradoNoStorageError(
                "Arquivo do documento não disponível para download no storage."
            ) from exc

    async def gerar_url_download(
        self, token: str, expiracao_segundos: int = 300
    ) -> DownloadResult:
        """Generate short-lived presigned URL, ensuring storage on demand."""
        doc_id = self.parse_token(token)
        stmt = select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
        res = await self._session.execute(stmt)
        doc = res.scalar_one_or_none()
        if doc is None:
            raise NotFoundError(_MSG_DOC_AUSENTE)

        s3_key = doc.chave_s3 or self.build_s3_key(
            doc.organizacao_id, doc.atendimento_id, doc.id
        )
        await self._garantir_documento_no_storage(doc, s3_key)
        url = await self._storage.gerar_url_pre_assinada(
            chave=s3_key, expiracao_segundos=expiracao_segundos
        )
        return DownloadResult(
            documento_id=doc.id,
            download_url=url,
            expires_in_seconds=expiracao_segundos,
            chave_s3=s3_key,
        )
