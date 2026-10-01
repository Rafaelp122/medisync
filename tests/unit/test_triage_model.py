"""Unit tests for Triage clinical model, risk classification, and SAMU 192 escape."""

from uuid import UUID

import pytest
from src.core.errors import DomainError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.triage.application.ports import EmergencyAlertDTO
from src.modules.triage.application.services import TriageService
from src.modules.triage.domain.classification import (
    SINAIS_ALARME_NIVEL_1,
    calcular_hash_tcle,
    classificar_risco_clinico,
)
from src.modules.triage.domain.exceptions import (
    EmergenciaCriticaSamuError,
    TriagemInvalidaError,
)
from src.modules.triage.domain.models import Triagem


def test_triage_exceptions_attributes() -> None:
    err_samu = EmergenciaCriticaSamuError(
        "Parada cardiorrespiratória detectada. Acione 192 imediatamente."
    )
    assert isinstance(err_samu, DomainError)
    assert err_samu.status_code == 422
    assert err_samu.code == "EMERGENCIA_CRITICA_SAMU_192"

    err_invalid = TriagemInvalidaError("Queixa principal não pode ser vazia.")
    assert isinstance(err_invalid, ValidationError)
    assert err_invalid.status_code == 422


def test_calcular_hash_tcle() -> None:
    termo = "Termo de Consentimento Livre e Esclarecido do PA Digital 24/7."
    h = calcular_hash_tcle(termo)
    assert isinstance(h, str)
    assert len(h) == 64
    assert h.islower()
    # SHA-256 é determinístico
    assert h == calcular_hash_tcle(termo)
    assert h != calcular_hash_tcle(termo + " extra")


def test_classificar_risco_nivel_1_emergencia_red_flags() -> None:
    # Qualquer discriminador de nível 1 leva a Prioridade 1 (Emergência)
    for sinal in SINAIS_ALARME_NIVEL_1:
        prioridade = classificar_risco_clinico(
            queixa_principal="Mal-estar súbito",
            sintomas=[sinal],
            escala_dor=0,
        )
        assert prioridade == 1

    # Queixa contendo gatilhos críticos diretamente
    prioridade_queixa = classificar_risco_clinico(
        queixa_principal="Paciente inconsciente sem respirar",
        sintomas=[],
        escala_dor=0,
    )
    assert prioridade_queixa == 1


def test_classificar_risco_niveis_2_a_5() -> None:
    # Nível 2 (Muito Urgente): Dor severa (8-10) ou queixas agudas graves
    p2 = classificar_risco_clinico(
        queixa_principal="Cefaleia súbita e intensa",
        sintomas=["cefaleia_intensa"],
        escala_dor=9,
    )
    assert p2 == 2

    # Nível 2 por sintoma sem dor alta
    p2_sintoma = classificar_risco_clinico(
        queixa_principal="Cefaleia",
        sintomas=["cefaleia_intensa"],
        escala_dor=2,
    )
    assert p2_sintoma == 2

    # Nível 3 (Urgente): Dor moderada (5-7) ou febre persistente
    p3 = classificar_risco_clinico(
        queixa_principal="Febre e tosse produtiva há 3 dias",
        sintomas=["febre"],
        escala_dor=5,
    )
    assert p3 == 3

    # Nível 3 por sintoma sem dor alta
    p3_sintoma = classificar_risco_clinico(
        queixa_principal="Náuseas e vômitos",
        sintomas=["vomitos_persistentes"],
        escala_dor=1,
    )
    assert p3_sintoma == 3

    # Nível 4 (Pouco Urgente): Dor leve (1-4) ou sintomas subagudos
    p4 = classificar_risco_clinico(
        queixa_principal="Dor de garganta leve e coriza",
        sintomas=["coriza"],
        escala_dor=3,
    )
    assert p4 == 4

    # Nível 5 (Não Urgente): Sem dor relevante (0) e sem sintomas de alerta
    p5 = classificar_risco_clinico(
        queixa_principal="Renovação de receita de uso contínuo",
        sintomas=[],
        escala_dor=0,
    )
    assert p5 == 5


def test_classificar_risco_validacao_inputs() -> None:
    with pytest.raises(
        TriagemInvalidaError, match="Queixa principal não pode ser vazia"
    ):
        classificar_risco_clinico("", [])

    with pytest.raises(
        TriagemInvalidaError, match="Escala de dor deve ser entre 0 e 10"
    ):
        classificar_risco_clinico("Queixa", [], escala_dor=-1)

    with pytest.raises(
        TriagemInvalidaError, match="Escala de dor deve ser entre 0 e 10"
    ):
        classificar_risco_clinico("Queixa", [], escala_dor=11)


def test_triagem_model_creation_and_defaults() -> None:
    atendimento_id = uuid7()
    triagem = Triagem(
        organizacao_id=1,
        atendimento_id=atendimento_id,
        queixa_principal="Febre e calafrios",
        sintomas_alerta=["febre"],
        prioridade_calculada=3,
    )

    assert isinstance(triagem.id, UUID)
    assert triagem.organizacao_id == 1
    assert triagem.atendimento_id == atendimento_id
    assert triagem.queixa_principal == "Febre e calafrios"
    assert triagem.sintomas_alerta == ["febre"]
    assert triagem.alerta_samu_disparado is False
    assert triagem.prioridade_calculada == 3
    assert triagem.is_emergencia_critica is False
    assert triagem.avaliado_em is not None


def test_triagem_model_validations() -> None:
    atendimento_id = uuid7()

    with pytest.raises(TriagemInvalidaError, match="organizacao_id inválido"):
        Triagem(
            organizacao_id=0,
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=3,
        )

    with pytest.raises(
        TriagemInvalidaError, match="Queixa principal não pode ser vazia"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="   ",
            prioridade_calculada=3,
        )

    with pytest.raises(
        TriagemInvalidaError, match="Prioridade calculada deve ser entre 1 e 5"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=0,
        )

    with pytest.raises(
        TriagemInvalidaError, match="Prioridade calculada deve ser entre 1 e 5"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=6,
        )


def test_triagem_disparar_alerta_samu_e_emergencia() -> None:
    atendimento_id = uuid7()
    triagem = Triagem(
        organizacao_id=1,
        atendimento_id=atendimento_id,
        queixa_principal="Dor torácica com irradiação para o braço",
        sintomas_alerta=["dor_toracica_irradiada"],
        prioridade_calculada=1,
    )

    assert triagem.is_emergencia_critica is True
    assert triagem.alerta_samu_disparado is False

    triagem.disparar_alerta_samu()
    assert triagem.alerta_samu_disparado is True
    assert triagem.is_emergencia_critica is True


def test_triagem_adicionar_sintoma_alerta() -> None:
    triagem = Triagem(
        organizacao_id=1,
        atendimento_id=uuid7(),
        queixa_principal="Tosse",
        sintomas_alerta=["tosse"],
        prioridade_calculada=4,
    )

    triagem.adicionar_sintoma_alerta("febre")
    assert "febre" in triagem.sintomas_alerta

    # Não duplica sintoma
    triagem.adicionar_sintoma_alerta("febre")
    assert triagem.sintomas_alerta.count("febre") == 1


class MockEmergencyNotifier:
    """Mock implementation of EmergencyNotifierPort for unit testing."""

    def __init__(self) -> None:
        self.notificacoes: list[EmergencyAlertDTO] = []

    async def notificar_emergencia_samu(self, alert: EmergencyAlertDTO) -> None:
        self.notificacoes.append(alert)


@pytest.mark.asyncio
async def test_triage_service_regular_case() -> None:
    notifier = MockEmergencyNotifier()
    service = TriageService(emergency_notifier=notifier)

    atendimento_id = uuid7()
    res = await service.avaliar_e_submeter_triagem(
        organizacao_id=1,
        atendimento_id=atendimento_id,
        queixa_principal="Dor de garganta leve",
        sintomas=["dor_garganta"],
        escala_dor=3,
        tcle_termo_texto="Termo de aceite",
    )

    assert res.prioridade_clinica == 4
    assert res.admissao_bloqueada is False
    assert res.alerta_samu_disparado is False
    assert len(res.tcle_hash) == 64
    assert len(notifier.notificacoes) == 0


@pytest.mark.asyncio
async def test_triage_service_emergency_samu_blocks_admission() -> None:
    notifier = MockEmergencyNotifier()
    service = TriageService(emergency_notifier=notifier)
    atendimento_id = uuid7()

    # Cenário com raise_on_emergency=True (padrão de proteção clínica)
    with pytest.raises(EmergenciaCriticaSamuError, match="Emergência médica crítica"):
        await service.avaliar_e_submeter_triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Dor precordial opressiva irradiada",
            sintomas=["dor_toracica_irradiada"],
            escala_dor=10,
            tcle_termo_texto="Termo de aceite",
            raise_on_emergency=True,
        )

    assert len(notifier.notificacoes) == 1
    alerta = notifier.notificacoes[0]
    assert alerta.atendimento_id == atendimento_id
    assert alerta.organizacao_id == 1
    assert "SAMU" in alerta.instrucao_redirecionamento

    # Cenário com raise_on_emergency=False (retorna DTO informativo com bloqueio)
    res = await service.avaliar_e_submeter_triagem(
        organizacao_id=1,
        atendimento_id=atendimento_id,
        queixa_principal="Paciente inconsciente no solo",
        sintomas=["inconsciencia"],
        escala_dor=0,
        tcle_termo_texto="Termo de aceite",
        raise_on_emergency=False,
    )
    assert res.prioridade_clinica == 1
    assert res.admissao_bloqueada is True
    assert res.alerta_samu_disparado is True
    assert res.instrucao_redirecionamento is not None
    assert len(notifier.notificacoes) == 2
