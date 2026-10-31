"""Unit tests for Triage clinical model, risk classification, and SAMU 192 escape."""

from uuid import UUID

import pytest
from src.core.errors import DomainError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.triage.application.dtos import (
    ResultadoTriagemDTO,
    TriageRiskEvaluationDTO,
)
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
        TriagemInvalidaError, match=r"Queixa principal '.*' não pode ser vazia"
    ):
        classificar_risco_clinico("", [])

    with pytest.raises(TriagemInvalidaError, match=r"Escala de dor '.*' inválida"):
        classificar_risco_clinico("Queixa", [], escala_dor=-1)

    with pytest.raises(TriagemInvalidaError, match=r"Escala de dor '.*' inválida"):
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

    with pytest.raises(TriagemInvalidaError, match=r"organizacao_id '.*' inválido"):
        Triagem(
            organizacao_id=0,
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=3,
        )

    with pytest.raises(
        TriagemInvalidaError, match=r"Queixa principal '.*' não pode ser vazia"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="   ",
            prioridade_calculada=3,
        )

    with pytest.raises(
        TriagemInvalidaError, match=r"Prioridade calculada '.*' inválida"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=0,
        )

    with pytest.raises(
        TriagemInvalidaError, match=r"Prioridade calculada '.*' inválida"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=6,
        )

    with pytest.raises(TriagemInvalidaError, match=r"Escala de dor '.*' inválida"):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Dor leve",
            prioridade_calculada=4,
            escala_dor=12,
        )

    # Coerência clínica: queixa com PCR (nível 1) não pode ter prioridade 5
    with pytest.raises(
        TriagemInvalidaError, match=r"incoerente com a queixa e sintomas"
    ):
        Triagem(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            queixa_principal="Paciente em parada cardiorrespiratoria",
            sintomas_alerta=["parada_cardiorrespiratoria"],
            prioridade_calculada=5,
            escala_dor=0,
        )


def test_triagem_model_escala_dor_persistence() -> None:
    atendimento_id = uuid7()
    triagem = Triagem(
        organizacao_id=1,
        atendimento_id=atendimento_id,
        queixa_principal="Cefaleia intensa",
        sintomas_alerta=["cefaleia_intensa"],
        prioridade_calculada=2,
        escala_dor=8,
    )
    assert triagem.escala_dor == 8


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
async def test_triage_service_avaliar_risco_success() -> None:
    notifier = MockEmergencyNotifier()
    service = TriageService(emergency_notifier=notifier)

    # 1. Com texto do termo (calcula SHA-256)
    res_texto = await service.avaliar_risco(
        organizacao_id=1,
        queixa_principal="Cefaleia moderada",
        sintomas=["cefaleia_intensa"],
        escala_dor=6,
        tcle_texto="Termo de consentimento digital",
    )
    assert isinstance(res_texto, TriageRiskEvaluationDTO)
    assert res_texto.prioridade_clinica == 2
    assert len(res_texto.tcle_hash) == 64
    assert res_texto.tcle_hash == calcular_hash_tcle("Termo de consentimento digital")
    assert res_texto.alerta_samu_disparado is False
    assert res_texto.instrucao_redirecionamento is None
    assert res_texto.is_emergencia_critica is False
    assert len(notifier.notificacoes) == 0

    # 2. Com hash pré-calculado
    hash_pre = "a" * 64
    res_hash = await service.avaliar_risco(
        organizacao_id=1,
        queixa_principal="Dor de garganta leve",
        sintomas=[],
        escala_dor=2,
        tcle_hash=hash_pre,
    )
    assert res_hash.prioridade_clinica == 4
    assert res_hash.tcle_hash == hash_pre
    assert res_hash.alerta_samu_disparado is False
    assert res_hash.is_emergencia_critica is False


@pytest.mark.asyncio
async def test_triage_service_avaliar_risco_validacao_tcle() -> None:
    service = TriageService()

    with pytest.raises(ValidationError, match="Consentimento TCLE obrigatório"):
        await service.avaliar_risco(
            organizacao_id=1,
            queixa_principal="Febre",
            sintomas=[],
            tcle_texto="",
            tcle_hash=None,
        )

    with pytest.raises(ValidationError, match="Consentimento TCLE obrigatório"):
        await service.avaliar_risco(
            organizacao_id=1,
            queixa_principal="Febre",
            sintomas=[],
            tcle_texto="   ",
            tcle_hash="",
        )


@pytest.mark.asyncio
async def test_triage_service_avaliar_risco_emergencia_samu() -> None:
    notifier = MockEmergencyNotifier()
    service = TriageService(emergency_notifier=notifier)
    atendimento_id = uuid7()

    # raise_on_emergency=True (padrão)
    with pytest.raises(EmergenciaCriticaSamuError):
        await service.avaliar_risco(
            organizacao_id=1,
            queixa_principal="Parada respiratória em curso",
            sintomas=["parada_cardiorrespiratoria"],
            tcle_texto="TCLE Aceito",
            raise_on_emergency=True,
            atendimento_id=atendimento_id,
        )
    assert len(notifier.notificacoes) == 1
    assert notifier.notificacoes[0].atendimento_id == atendimento_id

    # raise_on_emergency=False
    res = await service.avaliar_risco(
        organizacao_id=1,
        queixa_principal="Parada respiratória em curso",
        sintomas=["parada_cardiorrespiratoria"],
        tcle_texto="TCLE Aceito",
        raise_on_emergency=False,
        atendimento_id=atendimento_id,
    )
    assert res.prioridade_clinica == 1
    assert res.alerta_samu_disparado is True
    assert res.is_emergencia_critica is True
    assert res.instrucao_redirecionamento is not None
    assert len(notifier.notificacoes) == 2


def test_resultado_triagem_dto_alignment_with_risk_evaluation() -> None:
    # 1. Verifica herança e polimorfismo
    eval_dto = TriageRiskEvaluationDTO(
        prioridade_clinica=1,
        tcle_hash="abc",
        alerta_samu_disparado=True,
        instrucao_redirecionamento="LIGUE 192",
    )
    res_dto = ResultadoTriagemDTO.from_evaluation(eval_dto)

    assert isinstance(res_dto, TriageRiskEvaluationDTO)
    assert res_dto.prioridade_clinica == 1
    assert res_dto.tcle_hash == "abc"
    assert res_dto.alerta_samu_disparado is True
    assert res_dto.admissao_bloqueada is True
    assert res_dto.is_emergencia_critica is True

    # 2. Caso não emergencial
    eval_regular = TriageRiskEvaluationDTO(
        prioridade_clinica=4,
        tcle_hash="def",
        alerta_samu_disparado=False,
    )
    res_regular = ResultadoTriagemDTO.from_evaluation(eval_regular)
    assert res_regular.admissao_bloqueada is False
    assert res_regular.is_emergencia_critica is False

    # 3. Post-init auto bloqueia se prioridade 1 mesmo quando admissao_bloqueada=False
    res_manual = ResultadoTriagemDTO(
        prioridade_clinica=1,
        tcle_hash="ghi",
        admissao_bloqueada=False,
    )
    assert res_manual.admissao_bloqueada is True
