"""Domain exceptions for SUS ambulatory production and BPA-I reporting."""

from src.core.errors import DomainError, NotFoundError


class CompetenciaInvalidaError(DomainError):
    """Lançada quando a competência informada diverge do formato YYYYMM (01 a 12).

    Regras: docs/explanation/domains/ambulatory-domain.md, US-11 e ADR-012.
    """

    status_code: int = 400
    title: str = "Competência Inválida"
    code: str = "COMPETENCIA_INVALIDA"

    def __init__(self, competencia: str) -> None:
        self.competencia = competencia
        detail = (
            f"Competência '{competencia}' inválida; esperado formato 'YYYYMM' "
            "com mês entre 01 e 12 (ex.: '202611')."
        )
        super().__init__(
            detail, status_code=self.status_code, title=self.title, code=self.code
        )


class ProducaoNaoEncontradaError(NotFoundError):
    """Lançada quando nenhum registro consolidado existe para a competência e tenant.

    Regras: docs/explanation/domains/ambulatory-domain.md, US-11 e ADR-012.
    """

    title: str = "Produção Ambulatorial Não Encontrada"
    code: str = "PRODUCAO_NAO_ENCONTRADA"

    def __init__(self, competencia: str, organizacao_id: int) -> None:
        self.competencia = competencia
        self.organizacao_id = organizacao_id
        detail = (
            f"Nenhum registro de produção ambulatorial consolidado encontrado "
            f"para a competência '{competencia}' na organização {organizacao_id}."
        )
        super().__init__(detail, title=self.title, code=self.code)
