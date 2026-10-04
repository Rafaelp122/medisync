"""LGPD pure masking helpers (CPF and person names)."""

_PREPOSICOES: frozenset[str] = frozenset({"de", "da", "do", "das", "dos", "e"})


def mascarar_cpf(cpf: str) -> str:
    """Mask CPF for LGPD compliance, showing only first and last digits."""
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if len(digits) != 11:
        return "***.***.***-**"
    return f"{digits[:3]}.***.***-{digits[-2:]}"


def mascarar_nome(nome: str) -> str:
    """Mask person name for LGPD compliance, keeping first letters of each word."""
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
