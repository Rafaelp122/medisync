"""Adaptador de qualificação cadastral SUS para teleconsulta pública (ADR-012, RN03)."""

from src.modules.ambulatory.application.dtos import (
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
)
from src.modules.ambulatory.domain.enums import StatusElegibilidade


class SusEligibilityAdapter:
    """Qualificação cadastral e isenção universal para instâncias públicas do SUS.

    Conforme o Art. 196 da CF/88, Portaria GM/MS nº 3.232/2024 e ADR-012, o acesso
    à saúde pública é universal e gratuito, com dispensa de autorização prévia de
    operadora privada e garantia de código autorizatório 'SUS-ISENTO'.
    Regras: docs/explanation/domains/ambulatory-domain.md
    Decisão: ADR-012
    docs/adrs/ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md
    """

    async def verificar_elegibilidade(
        self, requisicao: RequisicaoElegibilidade
    ) -> ResultadoElegibilidade:
        """Atesta a isenção universal e qualificação do atendimento público no SUS."""
        return ResultadoElegibilidade(
            aprovado=True,
            status=StatusElegibilidade.APROVADO,
            codigo_autorizacao="SUS-ISENTO",
        )
