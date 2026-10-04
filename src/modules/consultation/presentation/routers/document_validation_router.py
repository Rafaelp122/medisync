"""Public verification and presigned download router for clinical documents."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.modules.consultation.composition import (
    DocumentValidationServiceDep,
    ValidationRateLimiterDep,
)
from src.modules.consultation.presentation.dependencies import exigir_rate_limit
from src.modules.consultation.presentation.schemas import (
    DownloadUrlResponse,
    ValidarDocumentoResponse,
)

validation_router = APIRouter(
    prefix="/documents", tags=["Document Validation & Presigned Storage"]
)

_VALIDATE_LIMITE = 30
_DOWNLOAD_LIMITE = 20
_JANELA_SEGUNDOS = 60


@validation_router.get(
    "/validate/{token_validacao}",
    response_model=ValidarDocumentoResponse,
    status_code=status.HTTP_200_OK,
    summary="Validação pública de autenticidade de documento clínico (QR Code CFM/ITI)",
)
async def validar_documento(
    token_validacao: Annotated[str, Path(description="Token de validação ou UUID")],
    request: Request,
    service: DocumentValidationServiceDep,
    limiter: ValidationRateLimiterDep,
) -> ValidarDocumentoResponse:
    """Consulta pública da autenticidade com mascaramento LGPD."""
    ip = request.client.host if request.client else "127.0.0.1"
    await exigir_rate_limit(
        limiter, f"ip:{ip}:validate", _VALIDATE_LIMITE, _JANELA_SEGUNDOS
    )
    result = await service.validar_documento(token_validacao)
    return ValidarDocumentoResponse.model_validate(result)


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
    token_validacao: Annotated[str, Path(description="Token de validação ou UUID")],
    request: Request,
    service: DocumentValidationServiceDep,
    limiter: ValidationRateLimiterDep,
    redirect: Annotated[
        bool, Query(description="307 p/ S3 se true, JSON se false")
    ] = True,
    expiracao_segundos: Annotated[int, Query(ge=60, le=3600)] = 300,
) -> Response:
    """Gera Presigned URL de curta duração para download seguro mediado pelo S3."""
    ip = request.client.host if request.client else "127.0.0.1"
    await exigir_rate_limit(
        limiter, f"ip:{ip}:download", _DOWNLOAD_LIMITE, _JANELA_SEGUNDOS
    )
    result = await service.gerar_url_download(token_validacao, expiracao_segundos)
    if redirect:
        return RedirectResponse(url=result.download_url, status_code=307)
    payload = DownloadUrlResponse.model_validate(result)
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )
