"""Clinical risk classification engine and TCLE cryptographic hash utility."""

import hashlib
import unicodedata

from src.modules.triage.domain.exceptions import TriagemInvalidaError

SINAIS_ALARME_NIVEL_1: frozenset[str] = frozenset(
    {
        "parada_cardiorrespiratoria",
        "inconsciencia",
        "dor_toracica_irradiada",
        "dispneia_grave",
        "cianose",
        "convulsao_em_curso",
        "hemorragia_grave",
        "anafilaxia",
        "rebaixamento_consciencia",
        "queimadura_vias_aereas",
    }
)

_PALAVRAS_CHAVE_EMERGENCIA_NIVEL_1: tuple[str, ...] = (
    "inconsciente",
    "sem respirar",
    "parada cardiaca",
    "parada respiratoria",
    "choque anafilatico",
    "hemorragia grave",
    "convulsionando",
)


def _normalizar_texto(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def calcular_hash_tcle(texto_termo: str) -> str:
    """Calcula o hash SHA-256 do texto de consentimento forense (RN07, LGPD Art. 11).

    Regras: docs/explanation/domains/triage-domain.md.
    História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
    """
    digest = hashlib.sha256(texto_termo.encode("utf-8")).hexdigest()
    return digest.lower()


def classificar_risco_clinico(
    queixa_principal: str,
    sintomas: list[str],
    escala_dor: int = 0,
) -> int:
    """Classifica a prioridade de acolhimento de 1 (Emergência) a 5 (Não Urgente).

    Aplica salvaguarda imediata SAMU 192 (RN04) e protocolo Manchester/ACR (RN01, RN07).
    Regras: docs/explanation/domains/triage-domain.md.
    História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
    """
    if not queixa_principal or not queixa_principal.strip():
        raise TriagemInvalidaError(
            f"Queixa principal '{queixa_principal}' não pode ser vazia; "
            "esperado relato descritivo preenchido."
        )

    if escala_dor < 0 or escala_dor > 10:
        raise TriagemInvalidaError(
            f"Escala de dor '{escala_dor}' inválida; esperado valor entre 0 e 10."
        )

    sintomas_set = {s.strip().lower() for s in sintomas}
    queixa_norm = _normalizar_texto(queixa_principal)

    # 1. Checagem de Emergência Nível 1 (Salvaguarda RN04)
    if any(sinal in sintomas_set for sinal in SINAIS_ALARME_NIVEL_1):
        return 1

    if any(palavra in queixa_norm for palavra in _PALAVRAS_CHAVE_EMERGENCIA_NIVEL_1):
        return 1

    # 2. Nível 2 (Muito Urgente - Laranja)
    if escala_dor >= 8:
        return 2

    sintomas_nivel_2 = {"cefaleia_intensa", "dor_toracica_moderada", "confusao_mental"}
    if any(s in sintomas_set for s in sintomas_nivel_2):
        return 2

    # 3. Nível 3 (Urgente - Amarelo)
    if escala_dor >= 5:
        return 3

    sintomas_nivel_3 = {"febre", "vomitos_persistentes", "desidratacao_moderada"}
    if any(s in sintomas_set for s in sintomas_nivel_3):
        return 3

    # 4. Nível 4 (Pouco Urgente - Verde)
    if escala_dor >= 1 or len(sintomas_set) > 0:
        return 4

    # 5. Nível 5 (Não Urgente - Azul)
    return 5


class ClassificadorManchester:
    """Motor de classificação clínica Manchester/ACR com salvaguarda SAMU 192 e TCLE.

    Aplica salvaguarda imediata SAMU 192 (RN04) e protocolo Manchester/ACR (RN01, RN07).
    Regras: docs/explanation/domains/triage-domain.md.
    História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
    """

    classificar = staticmethod(classificar_risco_clinico)
