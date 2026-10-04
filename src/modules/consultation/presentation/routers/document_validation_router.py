"""Public verification and presigned download router for clinical documents."""

import contextlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from src.core.database import DbSessionDep
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.composition import PEPServiceDep
from src.modules.consultation.domain.models import DocumentoClinico
from src.modules.consultation.presentation.schemas import (
    ItemValidacaoResponse,
    ValidarDocumentoResponse,
)

validation_router = APIRouter(
    prefix="/documents", tags=["Document Validation & Presigned Storage"]
)


def mascarar_cpf(cpf: str) -> str:
    """Mask CPF for LGPD compliance, showing only first and last digits."""
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if len(digits) != 11:
        return "***.***.***-**"
    return f"{digits[:3]}.***.***-{digits[-2:]}"


_PREPOSICOES: frozenset[str] = frozenset({"de", "da", "do", "das", "dos", "e"})


def mascarar_nome(nome: str) -> str:
    """Mask patient name for LGPD compliance, keeping first letters of each word."""
    partes = nome.strip().split()
    if not partes:
        return "***"
    mascaradas: list[str] = []
    for p in partes:
        if p.lower() in _PREPOSICOES:
            mascaradas.append(p.lower())
        elif len(p) <= 1:
            mascaradas.append(p)
        else:
            mascaradas.append(f"{p[0]}{'*' * (len(p) - 1)}")
    return " ".join(mascaradas)


def _parse_token_as_uuid(token_validacao: str) -> UUID:
    """Parse validation token or raise HTTP 404."""
    try:
        return UUID(token_validacao.strip())
    except (ValueError, AttributeError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de validação inválido ou documento não encontrado.",
        ) from err


@validation_router.get(
    "/validate/{token_validacao}",
    response_model=ValidarDocumentoResponse,
    status_code=status.HTTP_200_OK,
    summary="Validação pública de autenticidade de documento clínico (QR Code CFM/ITI)",
)
async def validar_documento(
    token_validacao: Annotated[
        str, Path(description="Token de validação ou UUID do documento clínico")
    ],
    session: DbSessionDep,
    service: PEPServiceDep,
) -> ValidarDocumentoResponse:
    """Consulta pública da autenticidade e integridade do documento clínico.

    Exibe metadados de emissão e assinatura digital ICP-Brasil com mascaramento
    de dados pessoais sensíveis do paciente em estrita conformidade com a LGPD.
    """
    doc_id = _parse_token_as_uuid(token_validacao)

    stmt = (
        select(DocumentoClinico)
        .where(DocumentoClinico.id == doc_id)
        .options(selectinload(DocumentoClinico.itens))
    )
    res = await session.execute(stmt)
    doc = res.scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento clínico não encontrado ou token inválido.",
        )

    # 1. Organization details
    org_nome = "MediSync Pronto-Atendimento Virtual"
    org_res = await session.execute(
        text("SELECT razao_social, nome_fantasia FROM organizacoes WHERE id = :org_id"),
        {"org_id": doc.organizacao_id},
    )
    org_row = org_res.mappings().first()
    if org_row:
        org_nome = str(
            org_row.get("nome_fantasia") or org_row.get("razao_social") or org_nome
        )

    # 2. Physician details
    medico_nome = "Médico Assistente"
    medico_crm = "00000"
    medico_crm_uf = "BR"
    med_res = await session.execute(
        text("SELECT nome_completo, crm, crm_uf FROM profissionais WHERE id = :med_id"),
        {"med_id": doc.medico_id},
    )
    med_row = med_res.mappings().first()
    if med_row:
        medico_nome = str(med_row.get("nome_completo") or medico_nome)
        medico_crm = str(med_row.get("crm") or medico_crm)
        medico_crm_uf = str(med_row.get("crm_uf") or medico_crm_uf)

    # 3. Patient details with LGPD masking
    paciente_nome_mascarado = "P*******"
    paciente_cpf_mascarado = "***.***.***-**"
    pac_res = await session.execute(
        text(
            "SELECT p.nome_completo, p.cpf FROM atendimentos a "
            "JOIN pacientes p ON a.paciente_id = p.id WHERE a.id = :atend_id"
        ),
        {"atend_id": doc.atendimento_id},
    )
    pac_row = pac_res.mappings().first()
    if pac_row:
        raw_nome = str(pac_row.get("nome_completo") or "")
        raw_cpf = str(pac_row.get("cpf") or "")
        paciente_nome_mascarado = mascarar_nome(raw_nome)
        paciente_cpf_mascarado = mascarar_cpf(raw_cpf)

    is_assinado = service.is_documento_assinado(doc)
    status_doc = "ASSINADO" if is_assinado else "EMITIDO"

    itens_resp = [ItemValidacaoResponse.model_validate(it) for it in doc.itens]

    return ValidarDocumentoResponse(
        documento_id=doc.id,
        tipo_documento=str(doc.tipo_documento),
        status_documento=status_doc,
        sha256_hash=doc.sha256_hash,
        assinado_em=doc.assinado_em if is_assinado else None,
        emissor_medico_nome=medico_nome,
        emissor_medico_crm=medico_crm,
        emissor_medico_uf=medico_crm_uf,
        organizacao_nome=org_nome,
        paciente_nome_mascarado=paciente_nome_mascarado,
        paciente_cpf_mascarado=paciente_cpf_mascarado,
        assinatura_digital_valida=is_assinado,
        conformidade_icp_brasil=is_assinado,
        itens=itens_resp,
    )


@validation_router.get(
    "/download/{token_validacao}",
    summary="Download seguro do documento clínico via Presigned URL temporária",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=Response,
    responses={
        307: {"description": "Redirecionamento temporário para URL S3 pré-assinada"},
        200: {"description": "Payload com URL pré-assinada (quando redirect=false)"},
        404: {"description": "Documento não encontrado"},
    },
)
async def download_documento_presigned(
    token_validacao: Annotated[
        str, Path(description="Token de validação ou UUID do documento clínico")
    ],
    session: DbSessionDep,
    service: PEPServiceDep,
    redirect: Annotated[
        bool,
        Query(
            description=(
                "Se verdadeiro, redireciona 307 para o S3. Se falso, "
                "retorna JSON com URL."
            )
        ),
    ] = True,
    expiracao_segundos: Annotated[
        int,
        Query(
            ge=60,
            le=3600,
            description="Tempo de expiração da URL pré-assinada em segundos",
        ),
    ] = 300,
) -> Response:
    """Gera Presigned URL de curta duração para download seguro mediado pelo S3."""
    doc_id = _parse_token_as_uuid(token_validacao)

    stmt = select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
    res = await session.execute(stmt)
    doc = res.scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento clínico não encontrado ou token inválido.",
        )

    s3_key = doc.chave_s3
    if not s3_key:
        s3_key = (
            f"orgs/{doc.organizacao_id}/consultations/{doc.atendimento_id}/"
            f"documents/{doc.id}.pdf"
        )

    # Ensure document exists in storage
    if not await _garantir_documento_no_storage(service, doc, s3_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo do documento não disponível para download no storage.",
        )

    presigned_url = await service.storage.gerar_url_pre_assinada(
        chave=s3_key,
        expiracao_segundos=expiracao_segundos,
    )

    if redirect:
        return RedirectResponse(
            url=presigned_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    return JSONResponse(
        content={
            "documento_id": str(doc.id),
            "download_url": presigned_url,
            "expires_in_seconds": expiracao_segundos,
            "chave_s3": s3_key,
        },
        status_code=status.HTTP_200_OK,
    )


async def _garantir_documento_no_storage(
    service: PEPService, doc: DocumentoClinico, s3_key: str
) -> bool:
    """Check if document binary is in storage; if not, compile and persist it."""
    with contextlib.suppress(Exception):
        await service.storage.obter_documento(s3_key)
        return True

    try:
        pdf_bytes = await service.compilar_documento_pdf(doc.id)
        await service.storage.salvar_documento(s3_key, pdf_bytes)
        return True
    except Exception:
        return False
