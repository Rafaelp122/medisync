"""LGPD pure masking helpers (CPF and person names)."""

_PREPOSICOES: frozenset[str] = frozenset({"de", "da", "do", "das", "dos", "e"})


def mascarar_cpf(cpf: str) -> str:
    """Mascara dígitos centrais do CPF em conformidade com privacidade (LGPD Art. 11).

    Exibe exclusivamente os 3 primeiros e 2 últimos dígitos para conferência.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if len(digits) != 11:
        return "***.***.***-**"
    return f"{digits[:3]}.***.***-{digits[-2:]}"


def _mascarar_token_nome(parte: str) -> str:
    if parte.lower() in _PREPOSICOES:
        return parte.lower()
    if len(parte) <= 1:
        return parte
    return f"{parte[0]}{'*' * (len(parte) - 1)}"


def mascarar_nome(nome: str) -> str:
    """Ofusca prenome e sobrenome preservando iniciais e preposições (LGPD Art. 11).

    Garante minimização de dados identificadores em logs e visualizações operacionais.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    partes = nome.strip().split()
    if not partes:
        return "***"
    return " ".join(_mascarar_token_nome(p) for p in partes)
