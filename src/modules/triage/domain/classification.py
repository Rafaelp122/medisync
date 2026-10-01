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
    """Calcula o hash SHA-256 do texto de consentimento (RN07, LGPD Art. 11)."""
    digest = hashlib.sha256(texto_termo.encode("utf-8")).hexdigest()
    return digest.lower()


def classificar_risco_clinico(
    queixa_principal: str,
    sintomas: list[str],
    escala_dor: int = 0,
) -> int:
    """Classifica a prioridade de acolhimento de 1 (Emergência) a 5 (Não Urgente).

    Adota a taxonomia aberta neutra compatível com o ACR do SUS (RN01, RN-REG-03):
    - 1: Emergência (Vermelho) — Risco Iminente de Morte ou Instabilidade Grave
    - 2: Muito Urgente (Laranja) — Alta Gravidade / Dor Severa (8-10)
    - 3: Urgente (Amarelo) — Moderada Gravidade / Febre / Dor Moderada (5-7)
    - 4: Pouco Urgente (Verde) — Baixa Gravidade / Dor Leve (1-4)
    - 5: Não Urgente (Azul) — Eletivo / Sem dor ou sintomas agudos
    """
    if not queixa_principal or not queixa_principal.strip():
        raise TriagemInvalidaError("Queixa principal não pode ser vazia.")

    if escala_dor < 0 or escala_dor > 10:
        raise TriagemInvalidaError("Escala de dor deve ser entre 0 e 10.")

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
