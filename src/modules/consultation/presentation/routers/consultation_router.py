"""FastAPI router for PEP clinical SOAP workflow, prescriptions and TMA indicators."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import get_current_tenant_id
from src.core.database import get_db_session
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.domain.exceptions import ConsultaInvalidaError

consultation_router = APIRouter(tags=["teleconsulta-pep"])

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _resolve_tenant_id(provided: int | None) -> int:
    if provided is not None and provided > 0:
        return provided
    ctx_tenant = get_current_tenant_id()
    if ctx_tenant is not None and ctx_tenant > 0:
        return ctx_tenant
    return 1


class RegistrarSOAPRequest(BaseModel):
    """Payload to record or update SOAP clinical notes."""

    model_config = ConfigDict(extra="forbid")

    medico_id: UUID = Field(description="Identificador único do médico assistente")
    anamnese: str = Field(
        description="Subjetivo (S): Queixa, anamnese e história clínica"
    )
    conduta: str = Field(
        description="Plano (P): Conduta terapêutica, orientações e desfecho"
    )
    exame_fisico_virtual: str | None = Field(
        default=None,
        description="Objetivo (O): Exame físico por vídeo e sinais observados",
    )
    cid10_principal: str | None = Field(
        default=None,
        description="Avaliação (A): Código CID-10 principal da hipótese diagnóstica",
    )
    organizacao_id: int | None = Field(
        default=None,
        description="Identificador da organização de saúde",
    )


class ItemPrescricaoRequest(BaseModel):
    """Prescription medication item input."""

    model_config = ConfigDict(extra="forbid")

    medicamento: str = Field(
        description="Nome do princípio ativo ou medicamento comercial"
    )
    dosagem: str = Field(description="Dosagem (ex: 500mg, 10mg/ml)")
    posologia: str = Field(description="Instruções de uso (ex: 1 cp de 8 em 8 horas)")
    duracao: str | None = Field(default=None, description="Duração do tratamento")
    controle_especial: bool = Field(
        default=False,
        description="Indica se é substância da Lista C1",
    )


class ItemPrescricaoResponse(BaseModel):
    """Prescription medication item output."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    medicamento: str
    dosagem: str
    posologia: str
    duracao: str | None
    controle_especial: bool


class EmitirDocumentoRequest(BaseModel):
    """Payload to issue a digital clinical document."""

    model_config = ConfigDict(extra="forbid")

    medico_id: UUID = Field(description="Identificador único do médico")
    tipo_documento: str = Field(
        description="Tipo de documento clínico (RECEITA_SIMPLES, etc.)"
    )
    itens: list[ItemPrescricaoRequest] = Field(
        default_factory=list,
        description="Itens de medicamentos a prescrever",
    )
    chave_s3: str | None = Field(
        default=None, description="Chave de armazenamento S3/MinIO"
    )
    sha256_hash: str | None = Field(
        default=None, description="Hash SHA-256 do documento"
    )
    organizacao_id: int | None = Field(
        default=None, description="Identificador da organização"
    )


class ValidarPrescricaoRequest(BaseModel):
    """Payload to pre-validate a medication against controlled substances lists."""

    model_config = ConfigDict(extra="forbid")

    medicamento: str = Field(description="Nome do medicamento a validar")


class EvolucaoSOAPResponse(BaseModel):
    """Response containing recorded SOAP clinical evolution notes."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    anamnese: str
    exame_fisico_virtual: str | None
    cid10_principal: str | None
    conduta: str
    registrado_em: datetime
    is_finalizado: bool


class DocumentoClinicoResponse(BaseModel):
    """Response containing issued clinical document and child items."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    tipo_documento: str
    chave_s3: str
    sha256_hash: str
    assinado_em: datetime
    is_finalizado: bool
    itens: list[ItemPrescricaoResponse]


class FinalizarConsultaRequest(BaseModel):
    """Payload to conclude attendance and lock PEP records."""

    model_config = ConfigDict(extra="forbid")

    medico_id: UUID = Field(description="Identificador do médico assistente")
    organizacao_id: int | None = Field(
        default=None, description="Identificador da organização"
    )


class TMAStatusResponse(BaseModel):
    """Telemetry indicator for Average Consultation Time (TMA), enforcing RN06."""

    model_config = ConfigDict(extra="forbid")

    atendimento_id: UUID
    tempo_decorrido_segundos: int
    tma_planejado_segundos: int
    excedeu_tma: bool
    aviso_visual: str


@consultation_router.post(
    "/consultations/{atendimento_id}/soap",
    response_model=EvolucaoSOAPResponse,
    status_code=status.HTTP_200_OK,
    summary="Registra ou atualiza evolução clínica SOAP no prontuário eletrônico (PEP)",
)
async def salvar_evolucao_soap(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    request: RegistrarSOAPRequest,
    session: SessionDep,
) -> EvolucaoSOAPResponse:
    """Registra ou atualiza Subjetivo, Objetivo, Avaliação e Plano no PEP."""
    org_id = _resolve_tenant_id(request.organizacao_id)
    service = PEPService(session)
    command = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atendimento_id,
        organizacao_id=org_id,
        medico_id=request.medico_id,
        anamnese=request.anamnese,
        conduta=request.conduta,
        exame_fisico_virtual=request.exame_fisico_virtual,
        cid10_principal=request.cid10_principal,
    )
    evolucao = await service.salvar_evolucao_soap(command)
    await session.commit()
    await session.refresh(evolucao)

    return EvolucaoSOAPResponse(
        id=evolucao.id,
        atendimento_id=evolucao.atendimento_id,
        organizacao_id=evolucao.organizacao_id,
        medico_id=evolucao.medico_id,
        anamnese=evolucao.anamnese,
        exame_fisico_virtual=evolucao.exame_fisico_virtual,
        cid10_principal=evolucao.cid10_principal,
        conduta=evolucao.conduta,
        registrado_em=evolucao.registrado_em,
        is_finalizado=evolucao.is_finalizado,
    )


@consultation_router.get(
    "/consultations/{atendimento_id}/soap",
    response_model=EvolucaoSOAPResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtém a evolução clínica SOAP registrada para o atendimento",
)
async def obter_evolucao_soap(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    session: SessionDep,
) -> EvolucaoSOAPResponse:
    """Retorna as notas SOAP atuais do atendimento."""
    service = PEPService(session)
    resumo = await service.obter_prontuario(atendimento_id)
    if resumo.evolucao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma evolução clínica registrada para este atendimento.",
        )
    evolucao = resumo.evolucao
    return EvolucaoSOAPResponse(
        id=evolucao.id,
        atendimento_id=evolucao.atendimento_id,
        organizacao_id=evolucao.organizacao_id,
        medico_id=evolucao.medico_id,
        anamnese=evolucao.anamnese,
        exame_fisico_virtual=evolucao.exame_fisico_virtual,
        cid10_principal=evolucao.cid10_principal,
        conduta=evolucao.conduta,
        registrado_em=evolucao.registrado_em,
        is_finalizado=evolucao.is_finalizado,
    )


@consultation_router.post(
    "/consultations/{atendimento_id}/prescriptions/validate",
    status_code=status.HTTP_200_OK,
    summary="Valida substância medicamentosa contra Portaria SVS/MS nº 344/98",
)
async def validar_prescricao_medicamento(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    request: ValidarPrescricaoRequest,
    session: SessionDep,
) -> dict[str, str]:
    """Verifica se o medicamento exige talonário físico (Listas A/B)."""
    service = PEPService(session)
    service.validar_prescricao(request.medicamento)
    return {
        "status": "PERMITIDO",
        "medicamento": request.medicamento,
        "mensagem": "Substância autorizada para prescrição digital em telemedicina.",
    }


@consultation_router.post(
    "/consultations/{atendimento_id}/documents",
    response_model=DocumentoClinicoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Emite documento clínico eletrônico com itens de prescrição",
)
async def emitir_documento_clinico(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    request: EmitirDocumentoRequest,
    session: SessionDep,
) -> DocumentoClinicoResponse:
    """Emite receita ou atestado aplicando salvaguardas da Portaria 344/98."""
    org_id = _resolve_tenant_id(request.organizacao_id)
    service = PEPService(session)

    itens_dto = [
        CriarItemPrescricaoDTO(
            medicamento=it.medicamento,
            dosagem=it.dosagem,
            posologia=it.posologia,
            duracao=it.duracao,
            controle_especial=it.controle_especial,
        )
        for it in request.itens
    ]

    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=org_id,
        medico_id=request.medico_id,
        tipo_documento=request.tipo_documento,
        itens=itens_dto,
        chave_s3=request.chave_s3 or "",
        sha256_hash=request.sha256_hash or "",
    )

    doc = await service.emitir_documento(cmd)
    await session.commit()
    await session.refresh(doc)

    itens_resp = [
        ItemPrescricaoResponse(
            id=item.id,
            medicamento=item.medicamento,
            dosagem=item.dosagem,
            posologia=item.posologia,
            duracao=item.duracao,
            controle_especial=item.controle_especial,
        )
        for item in doc.itens
    ]

    return DocumentoClinicoResponse(
        id=doc.id,
        atendimento_id=doc.atendimento_id,
        organizacao_id=doc.organizacao_id,
        medico_id=doc.medico_id,
        tipo_documento=str(doc.tipo_documento),
        chave_s3=doc.chave_s3,
        sha256_hash=doc.sha256_hash,
        assinado_em=doc.assinado_em,
        is_finalizado=doc.is_finalizado,
        itens=itens_resp,
    )


@consultation_router.post(
    "/consultations/{atendimento_id}/finalize",
    status_code=status.HTTP_200_OK,
    summary="Conclui atendimento e bloqueia registros clínicos (Imutabilidade)",
)
async def finalizar_consulta(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    request: FinalizarConsultaRequest,
    session: SessionDep,
) -> dict[str, object]:
    """Finaliza teleconsulta travando edição e exclusão de evolução e documentos."""
    org_id = _resolve_tenant_id(request.organizacao_id)
    service = PEPService(session)
    cmd = FinalizarConsultaCommand(
        atendimento_id=atendimento_id,
        organizacao_id=org_id,
        medico_id=request.medico_id,
    )
    evolucao = await service.finalizar_consulta(cmd)
    await session.commit()

    return {
        "status": "FINALIZADO",
        "atendimento_id": str(atendimento_id),
        "is_finalizado": evolucao.is_finalizado,
        "mensagem": (
            "Consulta finalizada com sucesso. Registros PEP travados de forma imutável."
        ),
    }


@consultation_router.get(
    "/consultations/{atendimento_id}/tma-status",
    response_model=TMAStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta telemetria discreta de TMA sem desconexão forçada (RN06)",
)
async def obter_tma_status(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    session: SessionDep,
    iniciado_em: Annotated[
        datetime | None,
        Query(description="Data e hora de início do atendimento (UTC)"),
    ] = None,
    tma_planejado_segundos: Annotated[
        int,
        Query(
            ge=60,
            le=7200,
            description="Tempo Médio de Atendimento previsto em segundos",
        ),
    ] = 900,
) -> TMAStatusResponse:
    """Calcula telemetria de TMA respeitando a soberania médica (RN06)."""
    service = PEPService(session)
    inicio = iniciado_em or datetime.now(UTC)
    tma_dto = service.calcular_tma_status(
        atendimento_id=atendimento_id,
        iniciado_em=inicio,
        tma_planejado_segundos=tma_planejado_segundos,
    )
    return TMAStatusResponse(
        atendimento_id=tma_dto.atendimento_id,
        tempo_decorrido_segundos=tma_dto.tempo_decorrido_segundos,
        tma_planejado_segundos=tma_dto.tma_planejado_segundos,
        excedeu_tma=tma_dto.excedeu_tma,
        aviso_visual=tma_dto.aviso_visual,
    )


@consultation_router.get(
    "/consultations/{atendimento_id}/documents/{documento_id}/pdf",
    summary="Download do documento clínico compilado em padrão PDF/A com QR Code",
    status_code=status.HTTP_200_OK,
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Arquivo PDF/A válido com QR Code",
        },
        404: {"description": "Documento não encontrado"},
    },
)
@consultation_router.get(
    "/api/v1/consultations/{atendimento_id}/documents/{documento_id}/pdf",
    include_in_schema=False,
    response_class=Response,
)
async def obter_documento_pdf(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    documento_id: Annotated[
        UUID, Path(description="Identificador único do documento clínico")
    ],
    session: SessionDep,
) -> Response:
    """Retorna o documento clínico compilado em PDF/A com QR Code de verificação."""
    pep_service = PEPService(session)
    try:
        pdf_bytes = await pep_service.compilar_documento_pdf(documento_id)
    except ConsultaInvalidaError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{documento_id}.pdf"',
            "Content-Type": "application/pdf",
        },
    )
