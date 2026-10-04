"""FastAPI router for PEP clinical SOAP workflow, prescriptions and TMA indicators."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from src.core.database import DbSessionDep
from src.core.dependencies import TenantDep
from src.core.errors import ForbiddenError
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
from src.modules.consultation.presentation.dependencies import (
    AtendimentoIdPath,
    ClinicalAccessDep,
    DocumentoIdPath,
)
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

consultation_router = APIRouter(prefix="/consultations", tags=["teleconsulta-pep"])


def _require_matching_tenant(provided: int | None, tenant_id: int) -> int:
    """Obsolete body organizacao_id: diverge -> 403, coincide/ausente -> ignora."""
    if provided is not None and provided != tenant_id:
        raise ForbiddenError(
            "Organização do corpo diverge do tenant autenticado "
            "(cabeçalho X-Tenant-ID)."
        )
    return tenant_id


@consultation_router.post(
    "/{atendimento_id}/soap",
    response_model=EvolucaoSOAPResponse,
    status_code=status.HTTP_200_OK,
    summary="Registra ou atualiza evolução clínica SOAP no prontuário eletrônico (PEP)",
)
async def salvar_evolucao_soap(
    atendimento_id: AtendimentoIdPath,
    request: RegistrarSOAPRequest,
    session: DbSessionDep,
    tenant_id: TenantDep,
) -> EvolucaoSOAPResponse:
    """Registra ou atualiza Subjetivo, Objetivo, Avaliação e Plano no PEP."""
    org_id = _require_matching_tenant(request.organizacao_id, tenant_id)
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
    "/{atendimento_id}/soap",
    response_model=EvolucaoSOAPResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtém a evolução clínica SOAP registrada para o atendimento",
)
async def obter_evolucao_soap(
    atendimento_id: AtendimentoIdPath,
    session: DbSessionDep,
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
    "/{atendimento_id}/prontuario",
    response_model=ProntuarioResponse,
    status_code=status.HTTP_200_OK,
    summary="Acesso ao prontuário médico protegido por RBAC e ABAC clínico",
)
async def obter_prontuario_protegido(
    atendimento_id: AtendimentoIdPath,
    _user: ClinicalAccessDep,
    session: DbSessionDep,
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
    "/{atendimento_id}/prescriptions/validate",
    status_code=status.HTTP_200_OK,
    summary="Valida substância medicamentosa contra Portaria SVS/MS nº 344/98",
)
async def validar_prescricao_medicamento(
    atendimento_id: AtendimentoIdPath,
    request: ValidarPrescricaoRequest,
    session: DbSessionDep,
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
    "/{atendimento_id}/documents",
    response_model=DocumentoClinicoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Emite documento clínico eletrônico com itens de prescrição",
)
async def emitir_documento_clinico(
    atendimento_id: AtendimentoIdPath,
    request: EmitirDocumentoRequest,
    session: DbSessionDep,
    tenant_id: TenantDep,
) -> DocumentoClinicoResponse:
    """Emite receita ou atestado aplicando salvaguardas da Portaria 344/98."""
    org_id = _require_matching_tenant(request.organizacao_id, tenant_id)
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
    "/{atendimento_id}/finalize",
    status_code=status.HTTP_200_OK,
    summary="Conclui atendimento e bloqueia registros clínicos (Imutabilidade)",
)
async def finalizar_consulta(
    atendimento_id: AtendimentoIdPath,
    request: FinalizarConsultaRequest,
    session: DbSessionDep,
    tenant_id: TenantDep,
) -> dict[str, object]:
    """Finaliza teleconsulta travando edição e exclusão de evolução e documentos."""
    org_id = _require_matching_tenant(request.organizacao_id, tenant_id)
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
    "/{atendimento_id}/tma-status",
    response_model=TMAStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta telemetria discreta de TMA sem desconexão forçada (RN06)",
)
async def obter_tma_status(
    atendimento_id: AtendimentoIdPath,
    session: DbSessionDep,
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
    "/{atendimento_id}/documents/{documento_id}/pdf",
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
async def obter_documento_pdf(
    atendimento_id: AtendimentoIdPath,
    documento_id: DocumentoIdPath,
    session: DbSessionDep,
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
    "/{atendimento_id}/documents/{documento_id}/sign",
    response_model=AssinarDocumentoResponse,
    status_code=status.HTTP_200_OK,
    summary="Aplica assinatura digital PAdES ICP-Brasil no documento clínico via PSC",
)
async def assinar_documento(
    atendimento_id: AtendimentoIdPath,
    documento_id: DocumentoIdPath,
    payload: AssinarDocumentoRequest,
    session: DbSessionDep,
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
