"""Controlled substances blacklist validation under Portaria SVS/MS nº 344/98."""

import re
import unicodedata

from src.modules.consultation.domain.exceptions import PrescricaoFisicaObrigatoriaError

# Lista A (Talonário Amarelo - Entorpecentes)
_LISTA_A_SUBSTANCIAS: frozenset[str] = frozenset(
    {
        "morfina",
        "fentanil",
        "fentanila",
        "oxicodona",
        "metadona",
        "hidromorfona",
        "meperidina",
        "petidina",
        "remifentanil",
        "sufentanil",
        "alfentanil",
        "buprenorfina",
        "tapentadol",
        "hidrocodona",
        "opio",
    }
)

# Lista B1 e B2 (Talonário Azul - Psicotrópicos e Anorexígenos)
_LISTA_B_SUBSTANCIAS: frozenset[str] = frozenset(
    {
        # B1 - Psicotrópicos (Benzodiazepínicos e análogos)
        "alprazolam",
        "clonazepam",
        "diazepam",
        "lorazepam",
        "midazolam",
        "bromazepam",
        "clobazam",
        "flunitrazepam",
        "nitrazepam",
        "zolpidem",
        "zopiclona",
        "eszopiclona",
        "triazolam",
        "estazolam",
        "flurazepam",
        "clordiazepoxido",
        "cloxazolam",
        "prazepam",
        "medazepam",
        # Nomes comerciais frequentes comumente inseridos
        "rivotril",
        "valium",
        "frontal",
        "lexotan",
        "dormonid",
        # B2 - Anorexígenos
        "sibutramina",
        "femproporex",
        "anfepramona",
        "amfepramona",
        "mazindol",
    }
)

_TODAS_SUBSTANCIAS_PROIBIDAS: frozenset[str] = (
    _LISTA_A_SUBSTANCIAS | _LISTA_B_SUBSTANCIAS
)


def _normalizar_texto(texto: str) -> str:
    """Normalize text removing accents, punctuation and excess whitespace."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    sem_pontuacao = re.sub(r"[^a-zA-Z0-9\s]", " ", sem_acento.lower())
    return " ".join(sem_pontuacao.split())


def validar_substancia_permitida_telemedicina(medicamento: str) -> None:
    """Validate medication is not prohibited from digital prescription.

    Under Portaria SVS/MS nº 344/98 and CFM nº 2.314/2022, substances from
    Lists A (yellow notification) and B (blue notification) strictly require
    physical security paper pads and cannot be issued via digital prescription.

    Raises:
        PrescricaoFisicaObrigatoriaError: When a prohibited substance is detected.
    """
    texto_norm = _normalizar_texto(medicamento)
    palavras = set(texto_norm.split())

    for substancia in _TODAS_SUBSTANCIAS_PROIBIDAS:
        if substancia in palavras or (len(substancia) > 4 and substancia in texto_norm):
            raise PrescricaoFisicaObrigatoriaError(
                f"O medicamento '{medicamento}' contém substância restrita "
                f"('{substancia}') pertencente à Lista A ou B da Portaria "
                "SVS/MS nº 344/98. A legislação sanitária veda a prescrição "
                "digital em telemedicina e exige talonário físico de segurança."
            )
