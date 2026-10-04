"""Public verification and presigned download router for clinical documents."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.modules.consultation.composition import (
    DocumentValidationServiceDep,
    ValidationRateLimiterDep,
)
from src.modules.consultation.presentation.schemas import ValidarDocumentoResponse

validation_router = APIRouter(
    prefix="/documents", tags=["Document Validation & Presigned Storage"]
)

_VALIDATE_LIMITE = 30
_DOWNLOAD_LIMITE = 20
_JANELA_SEGUNDOS = 60


async def _exigir_rate_limit(
    limiter: ValidationRateLimiterDep,
    chave: str,
    limite: int,
) -> None:
    res = await limiter.verificar_e_incrementar(
        chave=chave, limite=limite, janela_segundos=_JANELA_SEGUNDOS
    )
    if not res.permitido:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas requisições. Tente novamente em instantes.",
            headers={"Retry-After": str(res.retry_after_segundos)},
        )


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
    await _exigir_rate_limit(limiter, f"ip:{ip}:validate", _VALIDATE_LIMITE)
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
    await _exigir_rate_limit(limiter, f"ip:{ip}:download", _DOWNLOAD_LIMITE)
    result = await service.gerar_url_download(token_validacao, expiracao_segundos)
    if redirect:
        return RedirectResponse(url=result.download_url, status_code=307)
    return JSONResponse(
        content={
            "documento_id": str(result.documento_id),
            "download_url": result.download_url,
            "expires_in_seconds": result.expires_in_seconds,
            "chave_s3": result.chave_s3,
        },
        status_code=status.HTTP_200_OK,
    )
