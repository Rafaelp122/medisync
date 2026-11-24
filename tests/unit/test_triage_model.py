"""Unit tests for Triage clinical model, risk classification, and SAMU 192 escape."""

import logging
from collections.abc import Callable
from uuid import UUID

import httpx
import pytest
from src.core.errors import DomainError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.triage.application.dtos import TriageRiskEvaluationDTO
from src.modules.triage.application.ports import EmergencyAlertDTO
from src.modules.triage.application.services import TriageService
from src.modules.triage.domain.classification import (
    SINAIS_ALARME_NIVEL_1,
    calcular_hash_tcle,
    classificar_risco_clinico,
    normalizar_sintomas,
)
from src.modules.triage.domain.exceptions import (
    EmergenciaCriticaSamuError,
    TriagemInvalidaError,
)
from src.modules.triage.domain.models import Triagem
from src.modules.triage.infrastructure.adapters import (
    SamuEmergencyNotifierAdapter,
)

from tests.doubles import FakeEmergencyNotifier


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
        atendimento_id=atendimento_id,
        queixa_principal="Febre e calafrios",
        sintomas_alerta=["febre"],
        prioridade_calculada=3,
    )

    assert isinstance(triagem.id, UUID)
    assert not hasattr(triagem, "organizacao_id")
    assert triagem.atendimento_id == atendimento_id
    assert triagem.queixa_principal == "Febre e calafrios"
    assert triagem.sintomas_alerta == ["febre"]
    assert triagem.alerta_samu_disparado is False
    assert triagem.prioridade_calculada == 3
    assert triagem.is_emergencia_critica is False
    assert triagem.avaliado_em is not None


def test_triagem_model_validations() -> None:
    atendimento_id = uuid7()

    with pytest.raises(
        TriagemInvalidaError, match=r"Queixa principal '.*' não pode ser vazia"
    ):
        Triagem(
            atendimento_id=atendimento_id,
            queixa_principal="   ",
            prioridade_calculada=3,
        )

    with pytest.raises(
        TriagemInvalidaError, match=r"Prioridade calculada '.*' inválida"
    ):
        Triagem(
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=0,
        )

    with pytest.raises(
        TriagemInvalidaError, match=r"Prioridade calculada '.*' inválida"
    ):
        Triagem(
            atendimento_id=atendimento_id,
            queixa_principal="Dor",
            prioridade_calculada=6,
        )

    with pytest.raises(TriagemInvalidaError, match=r"Escala de dor '.*' inválida"):
        Triagem(
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
            atendimento_id=atendimento_id,
            queixa_principal="Paciente em parada cardiorrespiratoria",
            sintomas_alerta=["parada_cardiorrespiratoria"],
            prioridade_calculada=5,
            escala_dor=0,
        )


def test_triagem_model_escala_dor_persistence() -> None:
    atendimento_id = uuid7()
    triagem = Triagem(
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


@pytest.mark.asyncio
async def test_triage_service_avaliar_risco_success() -> None:
    notifier = FakeEmergencyNotifier()
    service = TriageService(emergency_notifier=notifier)

    # 1. Com texto do termo (calcula SHA-256)
    res_texto = await service.avaliar_risco(
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
    assert len(notifier.sent_alerts) == 0

    # 2. Com hash pré-calculado
    hash_pre = "a" * 64
    res_hash = await service.avaliar_risco(
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
            queixa_principal="Febre",
            sintomas=[],
            tcle_texto="",
            tcle_hash=None,
        )

    with pytest.raises(ValidationError, match="Consentimento TCLE obrigatório"):
        await service.avaliar_risco(
            queixa_principal="Febre",
            sintomas=[],
            tcle_texto="   ",
            tcle_hash="",
        )


@pytest.mark.asyncio
async def test_triage_service_avaliar_risco_emergencia_samu() -> None:
    notifier = FakeEmergencyNotifier()
    service = TriageService(emergency_notifier=notifier)
    atendimento_id = uuid7()

    # raise_on_emergency=True (padrão)
    with pytest.raises(EmergenciaCriticaSamuError):
        await service.avaliar_risco(
            queixa_principal="Parada respiratória em curso",
            sintomas=["parada_cardiorrespiratoria"],
            tcle_texto="TCLE Aceito",
            raise_on_emergency=True,
            atendimento_id=atendimento_id,
        )
    assert len(notifier.sent_alerts) == 1
    assert notifier.sent_alerts[0].atendimento_id == atendimento_id

    # raise_on_emergency=False
    res = await service.avaliar_risco(
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
    assert len(notifier.sent_alerts) == 2


@pytest.mark.parametrize(
    ("sintoma_ui", "prioridade_esperada", "canonico"),
    [
        ("dor_no_peito", 1, "dor_toracica_irradiada"),
        ("falta_de_ar", 1, "dispneia_grave"),
        ("tontura_desmaio", 1, "inconsciencia"),
        ("sangramento_grave", 1, "hemorragia_grave"),
        ("febre_alta", 3, "febre"),
    ],
)
def test_aliases_red_flags_e_higienizacao_sintomas(
    sintoma_ui: str,
    prioridade_esperada: int,
    canonico: str,
) -> None:
    """PioraClinicaModal canonical aliases normalize deterministically (Issue #163)."""
    norm = normalizar_sintomas([" ", "", f" {sintoma_ui} ", canonico])
    assert norm == [canonico]
    assert classificar_risco_clinico("Queixa geral", [sintoma_ui], 0) == (
        prioridade_esperada
    )


def test_sintomas_em_branco_sao_ignorados_na_classificacao() -> None:
    """Whitespace-only symptoms must not inflate classification above Level 5."""
    assert normalizar_sintomas([" ", "", "   "]) == []
    assert classificar_risco_clinico("Consulta de rotina", [" ", ""], 0) == 5


def test_triagem_criar_avaliada_classifica_e_dispara_samu_nivel_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Triagem.criar_avaliada() classifies 1x and sets SAMU flag on Level 1."""
    calls = 0

    def _spy_classificar(
        queixa_principal: str,
        sintomas: object,
        escala_dor: int = 0,
    ) -> int:
        nonlocal calls
        calls += 1
        return 1

    monkeypatch.setattr(
        "src.modules.triage.domain.models.triagem.classificar_risco_clinico",
        _spy_classificar,
    )
    triagem = Triagem.criar_avaliada(
        atendimento_id=uuid7(),
        queixa_principal="Dor precordial intensa",
        sintomas=["dor_no_peito"],
        escala_dor=9,
    )
    assert calls == 1
    assert triagem.prioridade_calculada == 1
    assert triagem.alerta_samu_disparado is True
    assert triagem.sintomas_alerta == ["dor_toracica_irradiada"]


@pytest.mark.parametrize(
    "queixa_livre",
    [
        "Paciente com dor no peito intensa",
        "Falta de ar súbita em repouso",
        "Relato de desmaio em casa",
        "Paciente nao respira há 1 minuto",
        "Quadro de anafilaxia após medicação",
    ],
)
def test_palavras_chave_emergencia_nivel_1_expandidas(queixa_livre: str) -> None:
    """Expanded Level 1 emergency free-text keywords trigger Level 1."""
    assert classificar_risco_clinico(queixa_livre, [], 0) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_hash", ["abc", "g" * 64, "A" * 63])
async def test_triage_service_rejeita_tcle_hash_malformado(bad_hash: str) -> None:
    """TriageService.avaliar_risco must validate SHA-256 regex ^[0-9a-f]{64}$."""
    service = TriageService()
    with pytest.raises(ValidationError, match=r"\^\[0-9a-f\]\{64\}\$"):
        await service.avaliar_risco(
            queixa_principal="Cefaleia leve",
            sintomas=[],
            escala_dor=2,
            tcle_hash=bad_hash,
        )


def _mock_httpx_client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
    orig_client: type[httpx.AsyncClient],
) -> Callable[..., httpx.AsyncClient]:
    def _factory(**kwargs: object) -> httpx.AsyncClient:
        return orig_client(transport=httpx.MockTransport(handler))

    return _factory


@pytest.mark.asyncio
async def test_samu_notifier_adapter_raise_for_status_e_log_erro(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SamuEmergencyNotifierAdapter invokes raise_for_status and logs HTTP errors."""
    captured_payloads: list[bytes] = []

    def _ok_handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(request.content)
        return httpx.Response(status_code=202, json={"ok": True})

    def _fail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, text="SAMU Gateway Error")

    alert = EmergencyAlertDTO(
        atendimento_id=uuid7(),
        queixa_principal="Dor torácica intensa",
        sintomas_alerta=["dor_toracica_irradiada"],
    )

    ok_adapter = SamuEmergencyNotifierAdapter(
        webhook_url="https://samu.example.invalid/hook"
    )
    assert not hasattr(ok_adapter, "sent_alerts")
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _mock_httpx_client_factory(_ok_handler, orig_client),
    )
    await ok_adapter.notificar_emergencia_samu(alert)
    assert len(captured_payloads) == 1

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _mock_httpx_client_factory(_fail_handler, orig_client),
    )
    with caplog.at_level(logging.ERROR):
        await ok_adapter.notificar_emergencia_samu(alert)
    assert (
        "HTTP 500" in caplog.text or "SAMU" in caplog.text or len(caplog.records) >= 1
    )
