"""Clinical document lifecycle service with canonical storage keys.

Owns validar_prescricao/emitir/compilar/assinar for DocumentoClinico using
ClinicalPdfCompiler and SignedCachePort with DB authoritative fallback.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
    EmitirDocumentoClinicoCommand,
    VerificarLivenessCommand,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.ports.document_directory_port import (
    DocumentDirectoryPort,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
)
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessChallengeDTO,
    LivenessVerificationPort,
    LivenessVerificationResultDTO,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.application.services.clinical_pdf_compiler import (
    ClinicalPdfCompiler,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    DocumentoClinicoNaoEncontradoError,
    LivenessChallengeInvalidoError,
    PrescricaoFisicaObrigatoriaError,
    ProvaDeVidaObrigatoriaError,
    SpoofingFacialDetectadoError,
    TravaAntiFraudeAtestadoError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    DocumentoItem,
    EvolucaoClinica,
    TipoDocumentoClinico,
)
from src.modules.consultation.domain.models._substances import (
    is_substancia_lista_c5,
    validar_substancia_permitida_telemedicina,
)
from src.modules.consultation.domain.s3_keys import build_signed_document_key

_PROHIBITED_DOC_TYPES = frozenset({"NOTIFICACAO_RECEITA_A", "NOTIFICACAO_RECEITA_B"})
_STATUS_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


def _resolve_liveness_actor(ator_papel: str) -> tuple[str, str]:
    """Resolve AtorTipo e AtorPapel canônicos para trilha de auditoria US-15."""
    normalized = ator_papel.strip().upper()
    if normalized == AtorPapel.PACIENTE.value:
        return AtorTipo.PACIENTE.value, AtorPapel.PACIENTE.value
    return AtorTipo.PROFISSIONAL.value, AtorPapel.MEDICO.value


def _is_valid_liveness_hash(value: str) -> bool:
    """Validate SHA-256 liveness verification proof format."""
    if value.startswith("sha256_") and len(value) >= 16:
        return True
    return len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value)


def _calcular_duracao_chamada_segundos(
    chamada_iniciada_em: datetime | None,
) -> float:
    """Compute elapsed consultation seconds strictly from call-start timestamp."""
    if chamada_iniciada_em is None:
        return 0.0
    inicio_utc = (
        chamada_iniciada_em
        if chamada_iniciada_em.tzinfo is not None
        else chamada_iniciada_em.replace(tzinfo=UTC)
    )
    return max(0.0, (datetime.now(UTC) - inicio_utc).total_seconds())


class DocumentoService:
    """Application service owning clinical document emit/compile/sign."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_generator: PDFGeneratorPort,
        signer: ICPBrasilSignerPort,
        storage: StoragePort,
        cache: SignedCachePort,
        atendimento_reader: AtendimentoReaderPort | None = None,
        directory: DocumentDirectoryPort | None = None,
        audit_trail: AuditTrailPort | None = None,
        liveness_verifier: LivenessVerificationPort | None = None,
        pdf_compiler: ClinicalPdfCompiler | None = None,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._signer = signer
        self._storage = storage
        self._cache = cache
        self._atendimento_reader = atendimento_reader
        self._directory = directory
        self._audit_trail = audit_trail
        self._liveness_verifier = liveness_verifier
        self._pdf_compiler = pdf_compiler or ClinicalPdfCompiler(
            session=session,
            pdf_generator=pdf_generator,
            storage=storage,
            directory=directory,
        )

    def validar_prescricao(self, medicamento: str) -> None:
        """Valida emissão digital de medicamento sob Portaria SVS/MS nº 344/98.

        Rejeita substâncias das Listas A/B que exigem talonário físico.
        Regras: Portaria 344/98 e docs/explanation/domains/consultation-domain.md.
        """
        validar_substancia_permitida_telemedicina(medicamento)

    async def solicitar_desafio_liveness(
        self, atendimento_id: UUID
    ) -> LivenessChallengeDTO:
        """Gera desafio de movimentação facial antes da emissão Lista C1 (US-15).

        Regras: RF-07, Portaria 344/98 Lista C1 e
        docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        if self._liveness_verifier is None:
            raise ConsultaInvalidaError(
                "Provedor de prova de vida facial (LivenessVerificationPort) não "
                f"configurado para atendimento {atendimento_id}."
            )
        return await self._liveness_verifier.gerar_desafio(atendimento_id)

    async def verificar_liveness_prescricao(
        self, command: VerificarLivenessCommand
    ) -> LivenessVerificationResultDTO:
        """Avalia prova de vida facial ativa para receita especial e registra auditoria.

        Bloqueia tentativas com suspeita de spoofing e persiste hash SHA-256.
        Regras: RF-07, LGPD Art. 11 e
        docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        if self._liveness_verifier is None:
            raise ConsultaInvalidaError(
                "Provedor de prova de vida facial (LivenessVerificationPort) não "
                f"configurado para atendimento {command.atendimento_id}."
            )
        result = await self._liveness_verifier.verificar_prova_de_vida(
            atendimento_id=command.atendimento_id,
            challenge_id=command.challenge_id,
            liveness_payload=command.liveness_payload,
        )
        if result.status == "DESAFIO_INVALIDO":
            raise LivenessChallengeInvalidoError(
                f"Desafio '{command.challenge_id}' inválido, expirado ou pertencente a "
                f"outro atendimento (recebido atendimento '{command.atendimento_id}')."
            )
        if result.status != "APROVADO" or result.liveness_score < 0.95:
            await self._registrar_auditoria_liveness(
                command, result, "SPOOFING_FACIAL_DETECTADO"
            )
            await self._session.commit()
            raise SpoofingFacialDetectadoError(
                f"Prova de vida facial reprovada para atendimento "
                f"{command.atendimento_id} (status='{result.status}', "
                f"score={result.liveness_score:.2f}; esperado status='APROVADO' com "
                "score >= 0.95)."
            )

        await self._registrar_auditoria_liveness(
            command, result, "LIVENESS_FACIAL_APROVADO"
        )
        await self._session.commit()
        return result

    async def _registrar_auditoria_liveness(
        self,
        command: VerificarLivenessCommand,
        result: LivenessVerificationResultDTO,
        tipo_evento: str,
    ) -> None:
        if self._audit_trail is None:
            return
        ator_tipo, ator_papel = _resolve_liveness_actor(command.ator_papel)
        await self._audit_trail.record_event(
            tipo_evento=tipo_evento,
            ator_tipo=ator_tipo,
            ator_papel=ator_papel,
            ator_id=command.ator_id,
            atendimento_id=command.atendimento_id,
            payload={
                "challenge_id": command.challenge_id,
                "status": result.status,
                "liveness_score": result.liveness_score,
                "verificacao_hash": result.verificacao_hash,
                "latitude": command.latitude,
                "longitude": command.longitude,
            },
        )

    @staticmethod
    def _requer_liveness_controle_especial(
        tipo_str: str, command: EmitirDocumentoClinicoCommand
    ) -> bool:
        """Verify whether prescription requires active facial liveness (US-15)."""
        if tipo_str == str(TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1):
            return True
        return any(
            item.controle_especial or is_substancia_lista_c5(item.medicamento)
            for item in command.itens
        )

    async def _validar_prova_de_vida_controle_especial(
        self, command: EmitirDocumentoClinicoCommand
    ) -> tuple[str | None, str | None]:
        clean_hash = (command.liveness_verificacao_hash or "").strip() or None
        excecao = (command.justificativa_excecao_liveness or "").strip()
        approved_hash = (
            await self._liveness_verifier.obter_hash_aprovado(command.atendimento_id)
            if self._liveness_verifier is not None
            else clean_hash
        )
        hash_matches = clean_hash is None or (
            approved_hash is not None and hmac.compare_digest(clean_hash, approved_hash)
        )
        if (
            approved_hash is not None
            and _is_valid_liveness_hash(approved_hash)
            and hash_matches
        ):
            return approved_hash, excecao or None
        if len(excecao) >= 10:
            return None, excecao
        raise ProvaDeVidaObrigatoriaError(
            "Emissão de receita de controle especial para atendimento "
            f"{command.atendimento_id} bloqueada: "
            f"liveness_verificacao_hash={clean_hash!r} "
            f"(aprovado no atendimento: {approved_hash!r}) "
            f"e justificativa_excecao_liveness={excecao!r} insuficientes; esperado "
            "hash SHA-256 de prova de vida aprovada para este atendimento ou "
            "justificativa clínica com ao menos 10 caracteres."
        )

    @property
    def storage(self) -> StoragePort:
        """Instância do StoragePort para persistência de documentos clínicos.

        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return self._storage

    @property
    def cache(self) -> SignedCachePort:
        """Porta de cache para status de assinatura digital ICP-Brasil.

        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return self._cache

    @property
    def directory(self) -> DocumentDirectoryPort | None:
        """Porta de diretório para dados de cabeçalho sob CFM nº 2.314/2022.

        Regras: docs/explanation/domains/consultation-domain.md.
        """
        return self._directory

    async def is_assinado(self, doc: DocumentoClinico) -> bool:
        """Verifica assinatura ativa em SignedCachePort com fallback no banco.

        Evita falsa expiração após TTL de 24h aquecendo o cache no hit em banco.
        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        if await self._cache.is_assinado(doc.id):
            return True
        assinado_em_banco = doc.assinado_em is not None and bool(
            (doc.sha256_hash or "").strip()
        )
        if assinado_em_banco:
            await self._cache.marcar_assinado(doc.id)
        return assinado_em_banco

    async def _obter_resumo_atendimento(
        self, atendimento_id: UUID
    ) -> AtendimentoResumoDTO | None:
        if self._atendimento_reader is None:
            return None
        return await self._atendimento_reader.obter_resumo(atendimento_id)

    async def _registrar_evento_trava_atestado(
        self,
        command: EmitirDocumentoClinicoCommand,
        duracao_segundos: float,
        justificativa: str,
        *,
        aceita: bool,
    ) -> None:
        if self._audit_trail is None:
            return
        await self._audit_trail.record_event(
            tipo_evento="TRAVA_TEMPORAL_ATESTADO_VIOLADA",
            ator_tipo=AtorTipo.PROFISSIONAL.value,
            ator_papel=AtorPapel.MEDICO.value,
            ator_id=command.medico_id,
            atendimento_id=command.atendimento_id,
            payload={
                "duracao_segundos": duracao_segundos,
                "justificativa": justificativa,
                "justificativa_aceita": aceita,
            },
        )

    async def _validar_trava_antifraude_atestado(
        self,
        command: EmitirDocumentoClinicoCommand,
        resumo: AtendimentoResumoDTO | None,
    ) -> None:
        """Aplica piso temporal real de 180s (chamada_iniciada_em) sob CFM 2.314/2022.

        Regras: CFM nº 2.314/2022, RN09 e
        docs/explanation/domains/consultation-domain.md.
        """
        if self._atendimento_reader is None or resumo is None:
            return

        duracao_segundos = _calcular_duracao_chamada_segundos(
            resumo.chamada_iniciada_em
        )
        if duracao_segundos >= 180.0:
            return

        justificativa = (command.justificativa_tempo_inferior or "").strip()
        if len(justificativa) >= 15:
            await self._registrar_evento_trava_atestado(
                command, duracao_segundos, justificativa, aceita=True
            )
            return

        await self._registrar_evento_trava_atestado(
            command, duracao_segundos, justificativa, aceita=False
        )
        raise TravaAntiFraudeAtestadoError(
            f"Emissão de atestado bloqueada: consulta durou "
            f"{duracao_segundos:.0f}s (inferior ao piso de 180s; "
            f"chamada_iniciada_em={resumo.chamada_iniciada_em!r}) e "
            f"justificativa '{justificativa}' é insuficiente; "
            "esperado mínimo de 15 caracteres circunstanciando a emissão célere."
        )

    async def _registrar_auditoria_emissao(
        self,
        doc: DocumentoClinico,
        command: EmitirDocumentoClinicoCommand,
        liveness_excecao: str | None,
    ) -> None:
        if self._audit_trail is None:
            return
        audit_payload: dict[str, object] = {
            "documento_id": str(doc.id),
            "tipo_documento": str(doc.tipo_documento),
            "itens_qtd": len(command.itens),
        }
        if liveness_excecao is not None:
            audit_payload["excecao_liveness"] = True
            audit_payload["justificativa_excecao_liveness"] = liveness_excecao
        await self._audit_trail.record_event(
            tipo_evento="DOCUMENTO_CLINICO_EMITIDO",
            ator_tipo=AtorTipo.PROFISSIONAL.value,
            ator_papel=AtorPapel.MEDICO.value,
            ator_id=command.medico_id,
            atendimento_id=command.atendimento_id,
            payload=audit_payload,
        )

    async def emitir_documento(
        self, command: EmitirDocumentoClinicoCommand
    ) -> DocumentoClinico:
        """Emite documento clínico validando substâncias da Portaria 344/98.

        Bloqueia receitas proibidas, aplica trava RN09 e valida estado terminal.
        Regras: Portaria 344/98, RN09 e ADR-006.
        """
        tipo_str = str(command.tipo_documento).strip().upper()
        if tipo_str in _PROHIBITED_DOC_TYPES:
            raise PrescricaoFisicaObrigatoriaError(
                f"O tipo de documento '{command.tipo_documento}' exige talonário "
                "físico impresso de segurança (Notificação de Receita Amarela/Azul) "
                "conforme a Portaria SVS/MS nº 344/98 e a Resolução CFM nº 2.314/2022. "
                "Sua emissão por telemedicina é expressamente vedada "
                f"(tipos restritos: {sorted(_PROHIBITED_DOC_TYPES)})."
            )

        resumo = await self._obter_resumo_atendimento(command.atendimento_id)
        if tipo_str == TipoDocumentoClinico.ATESTADO_MEDICO:
            await self._validar_trava_antifraude_atestado(command, resumo)

        liveness_hash: str | None = None
        liveness_excecao: str | None = None
        if self._requer_liveness_controle_especial(tipo_str, command):
            (
                liveness_hash,
                liveness_excecao,
            ) = await self._validar_prova_de_vida_controle_especial(command)

        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()
        is_term = bool(
            resumo is not None
            and (
                resumo.is_terminal or resumo.status.strip().upper() in _STATUS_TERMINAIS
            )
        )

        if (evolucao is not None and evolucao.is_finalizado) or is_term:
            if evolucao is not None:
                evolucao.marcar_finalizado()
            status_desc = "terminal" if is_term else "evolucao_finalizada"
            raise ConsultaFinalizadaError(
                "Não é permitido emitir documentos de consulta finalizada "
                f"(status atual: '{status_desc}')."
            )

        if evolucao is None or not evolucao.identidade_verificada:
            verificado = (
                evolucao.identidade_verificada if evolucao is not None else False
            )
            raise ConsultaInvalidaError(
                f"Atendimento '{command.atendimento_id}' bloqueado pela Resolução "
                f"CFM nº 2.314/2022: identidade_verificada={verificado!r} "
                f"(evolucao_presente={evolucao is not None}); é obrigatória a "
                "conferência visual prévia do documento oficial no prontuário SOAP "
                "antes da emissão de documentos clínicos."
            )

        new_doc_id = uuid7()
        # Valida cada item uma única vez via DocumentoItem.__init__ (Portaria 344/98)
        item_entities = [
            DocumentoItem(
                documento_id=new_doc_id,
                medicamento=item_dto.medicamento,
                dosagem=item_dto.dosagem,
                posologia=item_dto.posologia,
                duracao=item_dto.duracao,
                controle_especial=(
                    item_dto.controle_especial
                    or tipo_str
                    == str(TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1)
                ),
            )
            for item_dto in command.itens
        ]

        chave_s3 = (
            command.chave_s3.strip()
            if command.chave_s3 and command.chave_s3.strip()
            else build_signed_document_key(command.atendimento_id, new_doc_id)
        )
        sha256_hash = (
            command.sha256_hash.strip().lower()
            if command.sha256_hash and command.sha256_hash.strip()
            else None
        )

        doc = DocumentoClinico(
            atendimento_id=command.atendimento_id,
            medico_id=command.medico_id,
            tipo_documento=tipo_str,
            chave_s3=chave_s3,
            sha256_hash=sha256_hash,
            justificativa_tempo_inferior=command.justificativa_tempo_inferior,
            liveness_verificacao_hash=liveness_hash,
            justificativa_excecao_liveness=liveness_excecao,
            id=new_doc_id,
        )
        for item_entity in item_entities:
            doc.adicionar_item(item_entity)

        self._session.add(doc)
        self._session.add_all(item_entities)
        await self._session.flush()
        await self._registrar_auditoria_emissao(doc, command, liveness_excecao)
        await self._session.commit()
        return doc

    async def compilar_pdf(
        self,
        documento_id: UUID,
        *,
        atendimento_id: UUID | None = None,
    ) -> bytes:
        """Compila binário PDF/A-1b com QR Code ITI via ClinicalPdfCompiler.

        Garante conformidade com PAdES, CFM nº 2.314/2022 e isolamento Anti-IDOR.
        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return await self._pdf_compiler.compilar(
            documento_id, atendimento_id=atendimento_id
        )

    async def assinar(
        self,
        documento_id: UUID,
        atendimento_id: UUID,
        credenciais: DoctorCertificateCredentials,
    ) -> DocumentoAssinadoResult:
        """Assina digitalmente documento no padrão ICP-Brasil via Cloud PSC.

        Envia hash para assinatura e persiste artefato no Object Storage.
        Regras: MP nº 2.200-2/2001 e ADR-006.
        """
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

        if doc.atendimento_id != atendimento_id:
            raise DocumentoClinicoNaoEncontradoError(
                f"Documento '{documento_id}' não pertence ao "
                f"atendimento '{atendimento_id}'."
            )

        resumo = await self._obter_resumo_atendimento(doc.atendimento_id)
        is_term = bool(
            resumo is not None
            and (
                resumo.is_terminal or resumo.status.strip().upper() in _STATUS_TERMINAIS
            )
        )
        if doc.is_finalizado or is_term:
            status_desc = "terminal" if is_term else "documento_finalizado"
            raise ConsultaFinalizadaError(
                f"Não é permitido alterar ou assinar documento '{documento_id}' de "
                f"consulta já finalizada (status atual: '{status_desc}')."
            )

        pdf_bytes = await self.compilar_pdf(
            documento_id, atendimento_id=doc.atendimento_id
        )
        signed_bytes = await self._signer.assinar_pdf(pdf_bytes, credenciais)

        new_hash = hashlib.sha256(signed_bytes).hexdigest()
        doc.registrar_assinatura(new_hash, datetime.now(UTC))

        s3_key = build_signed_document_key(doc.atendimento_id, doc.id)
        await self._storage.salvar_documento(s3_key, signed_bytes)
        doc.chave_s3 = s3_key
        await self._cache.marcar_assinado(doc.id)
        await self._session.flush()
        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                tipo_evento="DOCUMENTO_CLINICO_ASSINADO",
                ator_tipo=AtorTipo.PROFISSIONAL.value,
                ator_papel=AtorPapel.MEDICO.value,
                ator_id=doc.medico_id,
                atendimento_id=doc.atendimento_id,
                payload={
                    "documento_id": str(doc.id),
                    "tipo_documento": str(doc.tipo_documento),
                    "sha256_hash": doc.sha256_hash,
                    "chave_s3": doc.chave_s3,
                },
            )
        await self._session.commit()

        assinado_em = doc.assinado_em or datetime.now(UTC)
        return DocumentoAssinadoResult(
            documento_id=doc.id,
            tipo_documento=str(doc.tipo_documento),
            sha256_hash=doc.sha256_hash or new_hash,
            assinado_em=assinado_em,
            tamanho_bytes=len(signed_bytes),
        )
