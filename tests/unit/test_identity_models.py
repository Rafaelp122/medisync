from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from src.core.errors import UnauthorizedError, ValidationError
from src.modules.identity.application.services.dependente_service import (
    DependenteService,
)
from src.modules.identity.application.services.onboarding_service import (
    OnboardingService,
)
from src.modules.identity.domain.exceptions import DependenteAutoReferenciaError
from src.modules.identity.domain.models import (
    ConfiguracaoUnidade,
    Dependente,
    Paciente,
    PacientePasskey,
    Profissional,
)
from src.modules.identity.domain.validators import validate_cns
from src.modules.identity.presentation.schemas import (
    CriarDependenteRequest,
    Fase1Request,
)

from tests.doubles import FakeAsyncSession, FakeResult


def test_configuracao_unidade_model_attributes_and_defaults() -> None:
    unidade = ConfiguracaoUnidade(
        cnpj="12.345.676/0001-90",
        razao_social="Hospital Municipal Santa Clara",
        nome_fantasia="HM Santa Clara",
        modo_publico_sus=True,
        cnes="2000001",
        ibge_municipio="355030",
    )
    assert unidade.id is not None
    assert unidade.singleton_guard is True
    assert unidade.cnpj == "12345676000190"  # Sanitize to digits
    assert unidade.cnes == "2000001"
    assert unidade.ibge_municipio == "355030"
    assert unidade.is_sus() is True
    assert unidade.ativo is True


def test_configuracao_unidade_invalid_cnpj_raises_validation_error() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            r"CNPJ '123' inválido: possui 3 dígitos; "
            r"esperados exatamente 14 dígitos numéricos\."
        ),
    ):
        ConfiguracaoUnidade(
            cnpj="123",
            razao_social="Clínica Exemplo",
            nome_fantasia="Exemplo",
        )


def test_configuracao_unidade_singleton_guard_rejects_false() -> None:
    with pytest.raises(ValidationError, match="singleton_guard"):
        ConfiguracaoUnidade(
            cnpj="12345678000199",
            razao_social="Unidade Unica",
            nome_fantasia="Unidade",
            singleton_guard=False,
        )


def test_configuracao_unidade_activation_toggle() -> None:
    unidade = ConfiguracaoUnidade(
        cnpj="12345678000199",
        razao_social="Posto de Saúde",
        nome_fantasia="Posto",
        ativo=True,
    )
    assert unidade.ativo is True
    unidade.desativar()
    assert unidade.ativo is False
    unidade.ativar()
    assert unidade.ativo is True


def test_profissional_medico_requires_crm_and_uf() -> None:
    with pytest.raises(ValidationError, match="CRM e UF são obrigatórios"):
        Profissional(
            cpf="123.456.789-00",
            nome_completo="Dr. Roberto Silva",
            email="roberto@medisync.com",
            papel="MEDICO",
            crm=None,
            crm_uf=None,
        )


def test_profissional_non_medico_allows_empty_crm() -> None:
    prof = Profissional(
        cpf="123.456.789-00",
        nome_completo="Gestor Carlos",
        email="carlos@medisync.com",
        papel="GESTOR_UNIDADE",
    )
    assert not hasattr(prof, "organizacao_id")
    assert prof.is_medico() is False
    assert prof.crm is None
    assert prof.crm_uf is None
    prof.desativar()
    assert prof.ativo is False
    prof.ativar()
    assert prof.ativo is True


def test_profissional_rejects_admin_global_papel() -> None:
    with pytest.raises(
        ValidationError, match=r"Papel do profissional 'ADMIN_GLOBAL' inválido"
    ):
        Profissional(
            cpf="123.456.789-00",
            nome_completo="Admin Obsoleto",
            email="admin@medisync.com",
            papel="ADMIN_GLOBAL",
        )


def test_profissional_invalid_cpf_raises_validation_error() -> None:
    with pytest.raises(
        ValidationError,
        match=r"CPF do profissional '\*\*\*\.\*\*\*\.\*\*\*-\*\*' inválido",
    ) as exc_info:
        Profissional(
            cpf="123",
            nome_completo="Carlos",
            email="carlos@medisync.com",
            papel="GESTOR_UNIDADE",
        )
    assert "123" not in exc_info.value.detail


def test_profissional_model_attributes_and_defaults() -> None:
    prof = Profissional(
        cpf="12345678900",
        nome_completo="Dra. Paula Souza",
        email="paula@medisync.com",
        papel="MEDICO",
        crm="123456",
        crm_uf="SP",
    )
    assert prof.nome_completo == "Dra. Paula Souza"
    assert prof.email == "paula@medisync.com"
    assert prof.crm == "123456"
    assert prof.crm_uf == "SP"
    assert prof.is_medico() is True
    assert prof.ativo is True


def test_paciente_pediatrico_without_cpf_succeeds_with_cns() -> None:
    paciente = Paciente(
        cpf=None,
        cns="123456789012345",
        data_nascimento=date.today(),
        nome_completo="Bebê Teste",
        telefone="(11) 98888-7777",
    )
    assert not hasattr(paciente, "organizacao_id")
    assert paciente.cpf is None
    assert paciente.cns == "123456789012345"
    assert paciente.is_pediatrico() is True


def test_paciente_adult_with_cpf_succeeds() -> None:
    paciente = Paciente(
        cpf="123.456.789-01",
        cns=None,
        data_nascimento=date(1990, 5, 20),
        nome_completo="Carlos Silva",
        telefone="11999998888",
    )
    assert paciente.cpf == "12345678901"
    assert paciente.is_pediatrico() is False


def test_paciente_without_cpf_and_without_cns_raises_validation_error() -> None:
    with pytest.raises(ValidationError, match="Obrigatório informar CPF ou CNS"):
        Paciente(
            cpf=None,
            cns=None,
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )


def test_paciente_invalid_cpf_length_raises_validation_error() -> None:
    with pytest.raises(
        ValidationError, match=r"CPF do paciente '\*\*\*\.\*\*\*\.\*\*\*-\*\*' inválido"
    ) as exc_info:
        Paciente(
            cpf="123",
            cns=None,
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )
    assert "123" not in exc_info.value.detail


def test_paciente_invalid_cns_length_raises_validation_error() -> None:
    with pytest.raises(ValidationError, match=r"CNS '\*\*\*' inválido") as exc_info:
        Paciente(
            cpf=None,
            cns="12345",
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )
    assert "12345" not in exc_info.value.detail


def test_paciente_alergias_management() -> None:
    paciente = Paciente(
        cpf="12345678901",
        data_nascimento=date(1995, 1, 1),
        telefone="11999998888",
    )
    assert paciente.alergias == []
    paciente.adicionar_alergia("Dipirona")
    paciente.adicionar_alergia("Penicilina")
    assert paciente.tem_alergia("dipirona") is True
    assert paciente.tem_alergia("Amoxicilina") is False
    paciente.remover_alergia("dipirona")
    assert paciente.tem_alergia("Dipirona") is False


def test_dependente_self_reference_raises_validation_error() -> None:
    same_id = uuid4()
    with pytest.raises(
        ValidationError, match="Paciente não pode ser dependente de si mesmo"
    ):
        Dependente(
            titular_id=same_id,
            dependente_id=same_id,
            grau_parentesco="FILHO",
        )


def test_dependente_auto_referencia_error_interpolates_ids() -> None:
    titular_id = uuid4()
    err = DependenteAutoReferenciaError(titular_id=titular_id, dependente_id=titular_id)
    assert str(titular_id) in err.detail
    assert "titular" in err.detail
    assert "dependente" in err.detail


def test_dependente_creation_succeeds() -> None:
    titular_id = uuid4()
    dep_id = uuid4()
    dep = Dependente(
        titular_id=titular_id,
        dependente_id=dep_id,
        grau_parentesco="filho",
    )
    assert not hasattr(dep, "organizacao_id")
    assert dep.titular_id == titular_id
    assert dep.dependente_id == dep_id
    assert dep.grau_parentesco == "FILHO"


def test_paciente_passkey_sem_organizacao_id() -> None:
    pac_id = uuid4()
    passkey = PacientePasskey(
        paciente_id=pac_id,
        credential_id="cred-123",
        public_key="pub-key-b64",
        sign_count=1,
        device_name="Chrome Linux",
    )
    assert not hasattr(passkey, "organizacao_id")
    assert passkey.paciente_id == pac_id
    assert passkey.credential_id == "cred-123"
    passkey.atualizar_contador(2)
    assert passkey.sign_count == 2


def test_paciente_com_nome_social_succeeds() -> None:
    paciente = Paciente(
        cpf="12345678901",
        data_nascimento=date(1990, 5, 20),
        nome_completo="Carlos Silva",
        nome_social="Carla Silva",
        telefone="11999998888",
    )
    assert paciente.nome_social == "Carla Silva"
    assert paciente.nome_completo == "Carlos Silva"


def test_profissional_papel_case_insensitive_and_validation() -> None:
    prof = Profissional(
        cpf="12345678901",
        nome_completo="Dr. João",
        email="joao@hospital.com",
        papel="medico",
        crm="123456",
        crm_uf="sp",
    )
    assert prof.papel == "MEDICO"
    assert prof.crm_uf == "SP"

    with pytest.raises(
        ValidationError, match=r"Papel do profissional 'ENFERMEIRO' inválido"
    ):
        Profissional(
            cpf="12345678901",
            nome_completo="Enf. João",
            email="joao@hospital.com",
            papel="ENFERMEIRO",
        )

    with pytest.raises(ValidationError, match=r"UF do CRM 'SPO' inválida"):
        Profissional(
            cpf="12345678901",
            nome_completo="Dr. João",
            email="joao@hospital.com",
            papel="medico",
            crm="123456",
            crm_uf="SPO",
        )


def test_paciente_validations_sexo_estado_cep() -> None:
    with pytest.raises(ValidationError, match=r"Sexo biológico 'X' inválido"):
        Paciente(
            cpf="12345678901",
            data_nascimento=date(1990, 1, 1),
            telefone="11999998888",
            sexo_biologico="X",
        )

    with pytest.raises(ValidationError, match=r"Estado \(UF\) 'SAOPAULO' inválido"):
        Paciente(
            cpf="12345678901",
            data_nascimento=date(1990, 1, 1),
            telefone="11999998888",
            estado="SAOPAULO",
        )

    with pytest.raises(ValidationError, match=r"CEP '123' inválido"):
        Paciente(
            cpf="12345678901",
            data_nascimento=date(1990, 1, 1),
            telefone="11999998888",
            cep="123",
        )


def test_paciente_completar_fase_2_metodo_rico() -> None:
    paciente = Paciente(
        cpf="12345678901",
        data_nascimento=date(1990, 1, 1),
        telefone="11999998888",
    )
    assert paciente.nome_mae is None

    paciente.completar_fase_2(
        nome_mae="Maria Souza",
        sexo_biologico="f",
        cep="01310-100",
        logradouro="Av Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="sp",
        nome_social="Mariana",
        alergias=["Dipirona", "Penicilina", "dipirona"],
    )

    assert paciente.nome_mae == "Maria Souza"
    assert paciente.sexo_biologico == "F"
    assert paciente.cep == "01310100"
    assert paciente.logradouro == "Av Paulista"
    assert paciente.numero == "1000"
    assert paciente.bairro == "Bela Vista"
    assert paciente.cidade == "São Paulo"
    assert paciente.estado == "SP"
    assert paciente.nome_social == "Mariana"
    assert paciente.alergias == ["Dipirona", "Penicilina"]

    with pytest.raises(ValidationError, match=r"Nome da mãe '' não pode ser vazio"):
        paciente.completar_fase_2(
            nome_mae="",
            sexo_biologico="F",
            cep="01310100",
            logradouro="Rua",
            numero="1",
            bairro="Bairro",
            cidade="Cidade",
            estado="SP",
        )


def test_mascaramento_cpf_cns_em_modelos_e_validate_cns() -> None:
    """Exceções em Paciente, Profissional e validate_cns não vazam CPF/CNS bruto."""
    raw_cpf = "1234567890"
    with pytest.raises(ValidationError) as exc_pac:
        Paciente(
            cpf=raw_cpf,
            data_nascimento=date(1990, 1, 1),
            telefone="11987654321",
            nome_completo="Teste",
        )
    assert raw_cpf not in exc_pac.value.detail

    with pytest.raises(ValidationError) as exc_prof:
        Profissional(
            cpf=raw_cpf,
            nome_completo="Dr. Teste",
            email="dr@test.com",
            papel="MEDICO",
            crm="12345",
            crm_uf="SP",
        )
    assert raw_cpf not in exc_prof.value.detail

    bad_cns = "898001234567890"
    with pytest.raises(ValidationError) as exc_cns:
        validate_cns(bad_cns)
    assert "898********7890" in exc_cns.value.detail
    assert bad_cns not in exc_cns.value.detail


def test_dependente_pediatrico_exige_outorga_tcle() -> None:
    """RN-IDE-05: vínculo de dependente menor exige outorga explícita de TCLE."""
    titular_id = uuid4()
    dep_id = uuid4()
    with pytest.raises(ValidationError, match="Outorga explícita de TCLE"):
        Dependente(
            titular_id=titular_id,
            dependente_id=dep_id,
            grau_parentesco="FILHO",
            outorga_tcle=False,
            is_pediatrico=True,
        )

    dep = Dependente(
        titular_id=titular_id,
        dependente_id=dep_id,
        grau_parentesco="FILHO",
        outorga_tcle=True,
        is_pediatrico=True,
    )
    assert dep.outorga_tcle is True


@pytest.mark.asyncio
async def test_onboarding_fase_1_ato_bloqueia_dob_divergente_e_protege_telefone() -> (
    None
):
    """Re-acolhimento exige data_nascimento igual, não altera tel e restringe token."""
    from typing import TYPE_CHECKING, cast

    from src.core.security import verify_intake_token

    if TYPE_CHECKING:
        from sqlalchemy.ext.asyncio import AsyncSession

    secret = "test-onboarding-secret-key-min-32-chars-ok"
    existente = Paciente(
        cpf="11144477735",
        data_nascimento=date(1985, 5, 15),
        telefone="11988887777",
        nome_completo="Maria Original",
        nome_social="Maria Social",
    )

    service_bad_dob = OnboardingService(
        session=cast("AsyncSession", FakeAsyncSession(results=[FakeResult(existente)])),
        secret_key=secret,
    )
    req_bad = Fase1Request(
        nome_completo="Atacante",
        data_nascimento=date(1999, 1, 1),
        telefone="11911112222",
        queixa_principal="Dor de cabeça",
        tcle_hash="a" * 64,
        cpf="11144477735",
    )
    with pytest.raises(UnauthorizedError, match="Dados civis divergentes"):
        await service_bad_dob.realizar_fase_1(req_bad)

    service_ok = OnboardingService(
        session=cast("AsyncSession", FakeAsyncSession(results=[FakeResult(existente)])),
        secret_key=secret,
    )
    req_ok = Fase1Request(
        nome_completo="Outro Nome Nao Deve Sobrescrever",
        nome_social="Outro Social",
        data_nascimento=date(1985, 5, 15),
        telefone="11911112222",
        queixa_principal="Febre persistente",
        tcle_hash="a" * 64,
        cpf="11144477735",
    )
    out = await service_ok.realizar_fase_1(req_ok)
    assert out.is_novo_paciente is False
    assert existente.telefone == "11988887777"
    assert existente.nome_completo == "Maria Original"
    assert existente.nome_social == "Maria Social"
    claims = verify_intake_token(out.token, secret)
    assert claims["is_novo_paciente"] is False


@pytest.mark.asyncio
async def test_dependente_service_exige_outorga_tcle_para_menor_e_libera_adulto() -> (
    None
):
    """RN-IDE-05: exige outorga_tcle=True quando dep_paciente.is_pediatrico()."""
    from typing import TYPE_CHECKING, cast

    if TYPE_CHECKING:
        from sqlalchemy.ext.asyncio import AsyncSession

    titular = Paciente(
        cpf="11144477735",
        data_nascimento=date(1985, 1, 1),
        telefone="11988887777",
        nome_completo="Titular Legal",
    )
    menor = Paciente(
        cns="700000000000005",
        data_nascimento=date(date.today().year - 10, 1, 1),
        telefone="11988887777",
        nome_completo="Menor Dependente",
    )
    adulto = Paciente(
        cpf="52998224725",
        data_nascimento=date(1960, 1, 1),
        telefone="11977776666",
        nome_completo="Dependente Idoso",
    )

    svc_reject = DependenteService(
        session=cast(
            "AsyncSession",
            FakeAsyncSession(results=[FakeResult(titular), FakeResult(menor)]),
        )
    )
    with pytest.raises(ValidationError, match="Outorga explícita de TCLE"):
        await svc_reject.adicionar_dependente(
            titular_id=titular.id,
            dados=CriarDependenteRequest(
                grau_parentesco="FILHO",
                dependente_id=menor.id,
                outorga_tcle=False,
            ),
        )

    svc_accept_minor = DependenteService(
        session=cast(
            "AsyncSession",
            FakeAsyncSession(
                results=[FakeResult(titular), FakeResult(menor), FakeResult(None)]
            ),
        )
    )
    res_minor = await svc_accept_minor.adicionar_dependente(
        titular_id=titular.id,
        dados=CriarDependenteRequest(
            grau_parentesco="FILHO",
            dependente_id=menor.id,
            outorga_tcle=True,
        ),
    )
    assert res_minor.outorga_tcle is True

    svc_accept_adult = DependenteService(
        session=cast(
            "AsyncSession",
            FakeAsyncSession(
                results=[FakeResult(titular), FakeResult(adulto), FakeResult(None)]
            ),
        )
    )
    res_adult = await svc_accept_adult.adicionar_dependente(
        titular_id=titular.id,
        dados=CriarDependenteRequest(
            grau_parentesco="GENITOR",
            dependente_id=adulto.id,
            outorga_tcle=False,
        ),
    )
    assert res_adult.outorga_tcle is False
    assert isinstance(datetime.now(UTC), datetime)
