"""FastAPI router for PEP clinical SOAP workflow, prescriptions and TMA indicators."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import get_current_tenant_id
from src.core.database import get_db_session
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.domain.exceptions import ConsultaInvalidaError
from src.modules.consultation.presentation.dependencies import ClinicalAccessDep
from src.modules.consultation.presentation.schemas import (
    AssinarDocumentoRequest,
    AssinarDocumentoResponse,
    DocumentoClinicoResponse,
    EmitirDocumentoRequest,
    EvolucaoSOAPResponse,
    FinalizarConsultaRequest,
    ProntuarioResponse,
    RegistrarSOAPRequest,
    TMAStatusResponse,
    ValidarPrescricaoRequest,
)

consultation_router = APIRouter(tags=["teleconsulta-pep"])

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _resolve_tenant_id(provided: int | None) -> int:
    if provided is not None and provided > 0:
        return provided
    ctx_tenant = get_current_tenant_id()
    if ctx_tenant is not None and ctx_tenant > 0:
        return ctx_tenant
    return 1


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

    return EvolucaoSOAPResponse.model_validate(evolucao)


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
    return EvolucaoSOAPResponse.model_validate(resumo.evolucao)


@consultation_router.get(
    "/consultations/{atendimento_id}/prontuario",
    response_model=ProntuarioResponse,
    status_code=status.HTTP_200_OK,
    summary="Acesso ao prontuário médico protegido por RBAC e ABAC clínico",
)
@consultation_router.get(
    "/atendimentos/{atendimento_id}/prontuario",
    response_model=ProntuarioResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def obter_prontuario_protegido(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    _user: ClinicalAccessDep,
    session: SessionDep,
) -> ProntuarioResponse:
    """Retorna o prontuário eletrônico mediante verificação em 3 camadas:
    1. Camada 1 (Macro RBAC): papel MEDICO.
    2. Camada 2 (RLS): isolamento de tenant.
    3. Camada 3 (ABAC Clínico): médico assistente + TCLE assinado + status ativo.
    """
    service = PEPService(session)
    resumo = await service.obter_prontuario(atendimento_id)

    evolucao_resp: EvolucaoSOAPResponse | None = None
    if resumo.evolucao is not None:
        evolucao_resp = EvolucaoSOAPResponse.model_validate(resumo.evolucao)

    documentos_resp = [
        DocumentoClinicoResponse.model_validate(doc) for doc in resumo.documentos
    ]

    return ProntuarioResponse(
        atendimento_id=atendimento_id,
        is_finalizado=resumo.is_finalizado,
        evolucao=evolucao_resp,
        documentos=documentos_resp,
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

    return DocumentoClinicoResponse.model_validate(doc)


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
    return TMAStatusResponse.model_validate(tma_dto)


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


@consultation_router.post(
    "/consultations/{atendimento_id}/documents/{documento_id}/sign",
    response_model=AssinarDocumentoResponse,
    status_code=status.HTTP_200_OK,
    summary="Aplica assinatura digital PAdES ICP-Brasil no documento clínico via PSC",
)
@consultation_router.post(
    "/api/v1/consultations/{atendimento_id}/documents/{documento_id}/sign",
    include_in_schema=False,
    response_model=AssinarDocumentoResponse,
)
async def assinar_documento(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    documento_id: Annotated[
        UUID, Path(description="Identificador único do documento clínico")
    ],
    payload: AssinarDocumentoRequest,
    session: SessionDep,
) -> AssinarDocumentoResponse:
    """Executa a assinatura digital PAdES em nuvem via PSC (CFM 2.314/2022)."""
    service = PEPService(session)
    creds = DoctorCertificateCredentials(
        token=payload.token,
        provider=payload.provider,
        certificate_alias=payload.certificate_alias,
    )
    try:
        doc, signed_bytes = await service.assinar_documento_clinico(
            documento_id=documento_id,
            credenciais=creds,
        )
    except ConsultaInvalidaError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err

    if doc.atendimento_id != atendimento_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Documento '{documento_id}' não pertence ao "
                f"atendimento '{atendimento_id}'."
            ),
        )

    await session.commit()
    return AssinarDocumentoResponse(
        documento_id=doc.id,
        tipo_documento=str(doc.tipo_documento),
        sha256_hash=doc.sha256_hash,
        assinado_em=doc.assinado_em,
        tamanho_bytes=len(signed_bytes),
    )
