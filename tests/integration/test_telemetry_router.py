"""Integration tests for shift telemetry and configuration endpoints."""

from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from src.core.authz.roles import Role
from src.core.valkey import get_valkey_pool

from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_obter_painel_telemetria_gestor_sucesso(
    async_client: AsyncClient,
) -> None:
    """Validate GET /painel returns operational metrics for GESTOR_UNIDADE."""
    gestor_id = uuid4()
    headers = auth_headers(papel=Role.GESTOR_UNIDADE, usuario_id=gestor_id)

    # 1. Primeira consulta: cache miss, computa métricas e armazena em cache
    resp = await async_client.get("/api/v1/telemetria/painel", headers=headers)
    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())

    assert "organizacao_id" not in data
    assert "gerado_em" in data
    assert "tme_medio_segundos" in data
    assert "tme_nivel_1_segundos" in data
    assert "tme_nivel_2_segundos" in data
    assert "tme_nivel_3_segundos" in data
    assert "tme_nivel_4_segundos" in data
    assert "tme_nivel_5_segundos" in data
    assert "tma_medio_segundos" in data
    assert isinstance(data["medicos_tma"], list)
    assert "no_show_rate" in data
    assert "evasao_rate" in data
    assert "sla_compliance_percentual" in data
    assert "sla_em_conformidade" in data
    assert "medicos_ativos_count" in data
    assert "total_pacientes_fila" in data
    assert "total_atendimentos" in data

    # 2. Validar que o painel foi armazenado no cache Valkey singleton com TTL
    valkey = Redis(connection_pool=get_valkey_pool())
    ttl = await valkey.ttl("telemetry:painel")
    assert ttl > 0
    assert ttl <= 5

    # 3. Segunda consulta: retorna do cache
    resp_cached = await async_client.get("/api/v1/telemetria/painel", headers=headers)
    assert resp_cached.status_code == 200
    data_cached = cast("dict[str, object]", resp_cached.json())
    assert data_cached["gerado_em"] == data["gerado_em"]

    # 4. Consulta forçando bypass de cache com desconsiderar_cache=true
    resp_bypass = await async_client.get(
        "/api/v1/telemetria/painel?desconsiderar_cache=true", headers=headers
    )
    assert resp_bypass.status_code == 200


@pytest.mark.asyncio
async def test_configuracao_plantao_lifecycle_get_e_put(
    async_client: AsyncClient,
) -> None:
    """Validate GET /config-plantao default initialization and PUT updates."""
    gestor_id = uuid4()
    headers = auth_headers(papel=Role.GESTOR_UNIDADE, usuario_id=gestor_id)

    # 1. GET inicial: cria e retorna default singleton para a unidade
    resp_get = await async_client.get(
        "/api/v1/telemetria/config-plantao", headers=headers
    )
    assert resp_get.status_code == 200
    cfg_init = cast("dict[str, object]", resp_get.json())

    assert "organizacao_id" not in cfg_init
    assert cfg_init["medicos_ativos_planejados"] == 1
    assert Decimal(str(cfg_init["alpha_backpressure"])) == Decimal("1.25")
    assert cfg_init["modo_operacao"] == "SUS"
    assert cfg_init["tma_padrao_segundos"] == 600
    assert cfg_init["tempo_tolerancia_ring_segundos"] == 45

    # 2. PUT: Atualiza parâmetros operacionais
    put_payload = {
        "medicos_ativos_planejados": 4,
        "alpha_backpressure": "1.28",
        "cota_diaria_maxima": 500,
        "tma_padrao_segundos": 720,
        "tempo_tolerancia_ring_segundos": 60,
        "modo_operacao": "PRIVADO",
        "sla_minutos_nivel_1": 1,
        "sla_minutos_nivel_2": 15,
        "sla_minutos_nivel_3": 45,
        "sla_minutos_nivel_4": 90,
        "sla_minutos_nivel_5": 180,
    }
    resp_put = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json=put_payload,
        headers=headers,
    )
    assert resp_put.status_code == 200
    cfg_updated = cast("dict[str, object]", resp_put.json())

    assert "organizacao_id" not in cfg_updated
    assert cfg_updated["medicos_ativos_planejados"] == 4
    assert Decimal(str(cfg_updated["alpha_backpressure"])) == Decimal("1.28")
    assert cfg_updated["cota_diaria_maxima"] == 500
    assert cfg_updated["tma_padrao_segundos"] == 720
    assert cfg_updated["tempo_tolerancia_ring_segundos"] == 60
    assert cfg_updated["modo_operacao"] == "PRIVADO"
    assert cfg_updated["sla_minutos_nivel_1"] == 1
    assert cfg_updated["sla_minutos_nivel_2"] == 15
    assert cfg_updated["atualizado_por_id"] == str(gestor_id)

    # 3. GET subsequente reflete alterações persistidas
    resp_get2 = await async_client.get(
        "/api/v1/telemetria/config-plantao", headers=headers
    )
    assert resp_get2.status_code == 200
    cfg_refetched = cast("dict[str, object]", resp_get2.json())
    assert cfg_refetched["medicos_ativos_planejados"] == 4
    assert Decimal(str(cfg_refetched["alpha_backpressure"])) == Decimal("1.28")
    assert cfg_refetched["modo_operacao"] == "PRIVADO"


@pytest.mark.asyncio
async def test_telemetria_permissoes_anonimo_e_paciente(
    async_client: AsyncClient,
) -> None:
    """Validate 401 for anonymous and 403 for PACIENTE role across all endpoints."""
    # 1. Requisição anônima sem Authorization header -> 401
    resp_anon_painel = await async_client.get("/api/v1/telemetria/painel")
    assert resp_anon_painel.status_code == 401

    resp_anon_cfg = await async_client.get("/api/v1/telemetria/config-plantao")
    assert resp_anon_cfg.status_code == 401

    resp_anon_put = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"medicos_ativos_planejados": 2},
    )
    assert resp_anon_put.status_code == 401

    # 2. Requisição com usuário PACIENTE -> 403 Forbidden
    paciente_headers = auth_headers(papel=Role.PACIENTE, usuario_id=uuid4())

    resp_pac_painel = await async_client.get(
        "/api/v1/telemetria/painel", headers=paciente_headers
    )
    assert resp_pac_painel.status_code == 403

    resp_pac_cfg = await async_client.get(
        "/api/v1/telemetria/config-plantao", headers=paciente_headers
    )
    assert resp_pac_cfg.status_code == 403

    resp_pac_put = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"medicos_ativos_planejados": 2},
        headers=paciente_headers,
    )
    assert resp_pac_put.status_code == 403


@pytest.mark.asyncio
async def test_configuracao_plantao_validacao_limites_422(
    async_client: AsyncClient,
) -> None:
    """Validate 422 Unprocessable Entity for invalid parameters on PUT."""
    gestor_id = uuid4()
    headers = auth_headers(papel=Role.GESTOR_UNIDADE, usuario_id=gestor_id)

    # 1. alpha < 1.20
    resp_low_alpha = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"alpha_backpressure": "1.19"},
        headers=headers,
    )
    assert resp_low_alpha.status_code == 422

    # 2. alpha > 1.30
    resp_high_alpha = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"alpha_backpressure": "1.31"},
        headers=headers,
    )
    assert resp_high_alpha.status_code == 422

    # 3. medicos_ativos_planejados < 1
    resp_zero_medicos = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"medicos_ativos_planejados": 0},
        headers=headers,
    )
    assert resp_zero_medicos.status_code == 422

    # 4. tma_padrao_segundos < 60
    resp_low_tma = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"tma_padrao_segundos": 59},
        headers=headers,
    )
    assert resp_low_tma.status_code == 422

    # 5. modo_operacao inválido
    resp_modo_invalido = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"modo_operacao": "MISTO"},
        headers=headers,
    )
    assert resp_modo_invalido.status_code == 422


@pytest.mark.asyncio
async def test_obter_painel_telemetria_medico_sucesso(
    async_client: AsyncClient,
) -> None:
    """Validate GET /painel returns operational metrics for Role.MEDICO.

    Conforms to US-13 and resolves NC-TEL-02.
    """
    medico_id = uuid4()
    headers = auth_headers(papel=Role.MEDICO, usuario_id=medico_id)

    resp = await async_client.get("/api/v1/telemetria/painel", headers=headers)
    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())

    assert "organizacao_id" not in data
    assert "tme_medio_segundos" in data
    assert "tma_medio_segundos" in data
    assert "sla_compliance_percentual" in data
    assert "sla_em_conformidade" in data
    assert "medicos_ativos_count" in data
    assert "total_pacientes_fila" in data
    assert "total_atendimentos" in data


@pytest.mark.asyncio
async def test_configuracao_plantao_medico_proibido(
    async_client: AsyncClient,
) -> None:
    """Validate 403 Forbidden for Role.MEDICO on /config-plantao (GET and PUT)."""
    medico_id = uuid4()
    headers = auth_headers(papel=Role.MEDICO, usuario_id=medico_id)

    # 1. GET /config-plantao proibido para médico
    resp_get = await async_client.get(
        "/api/v1/telemetria/config-plantao", headers=headers
    )
    assert resp_get.status_code == 403
    err_get = cast("dict[str, object]", resp_get.json())
    assert err_get["code"] == "FORBIDDEN"
    assert "MEDICO" in str(err_get["detail"])

    # 2. PUT /config-plantao proibido para médico
    resp_put = await async_client.put(
        "/api/v1/telemetria/config-plantao",
        json={"medicos_ativos_planejados": 3},
        headers=headers,
    )
    assert resp_put.status_code == 403
    err_put = cast("dict[str, object]", resp_put.json())
    assert err_put["code"] == "FORBIDDEN"
    assert "MEDICO" in str(err_put["detail"])


@pytest.mark.asyncio
@pytest.mark.parametrize("papel_proibido", [Role.PACIENTE, Role.FATURAMENTO])
async def test_obter_painel_telemetria_papeis_proibidos(
    async_client: AsyncClient,
    papel_proibido: Role,
) -> None:
    """Validate 403 Forbidden with offending value and expected shape."""
    headers = auth_headers(papel=papel_proibido, usuario_id=uuid4())

    resp = await async_client.get("/api/v1/telemetria/painel", headers=headers)
    assert resp.status_code == 403
    body = cast("dict[str, object]", resp.json())
    assert body["code"] == "FORBIDDEN"
    detail = str(body["detail"])
    assert papel_proibido.value in detail
    assert "MEDICO" in detail or "GESTOR_UNIDADE" in detail
