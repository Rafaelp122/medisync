from tests.factories.identity import (
    make_dependente,
    make_organizacao,
    make_paciente,
    make_profissional,
)


def test_factories_creation():
    org = make_organizacao()
    assert org.cnpj == "12345678000195"

    prof = make_profissional(org.id or 1)
    assert prof.is_medico() is True

    paciente = make_paciente(org.id or 1)
    assert paciente.cpf == "55566677788"

    dep = make_dependente(org.id or 1)
    assert dep.grau_parentesco == "FILHO"
