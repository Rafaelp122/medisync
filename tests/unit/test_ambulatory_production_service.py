"""Unit tests for SUS ambulatory production model and service (ADR-012, US-11)."""

from uuid import uuid4

import pytest
from src.modules.ambulatory.application.dtos import ConsolidarTeleconsultaCommand
from src.modules.ambulatory.application.services.producao_service import (
    ProducaoAmbulatorialService,
)
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)

from tests.doubles import FakeAsyncSession, FakeResult


class TestProducaoAmbulatorialModel:
    """Validações do modelo rico de Produção Ambulatorial SUS."""

    def test_criar_producao_ambulatorial_sucesso(self) -> None:
        atendimento_id = uuid4()
        profissional_id = uuid4()
        paciente_id = uuid4()

        producao = ProducaoAmbulatorial(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            profissional_id=profissional_id,
            paciente_id=paciente_id,
            cnes="1234567",
        )

        assert producao.organizacao_id == 1
        assert producao.atendimento_id == atendimento_id
        assert producao.profissional_id == profissional_id
        assert producao.paciente_id == paciente_id
        assert producao.cnes == "1234567"
        assert producao.codigo_sigtap == "03.01.01.025-0"
        assert producao.carater_atendimento == "02"
        assert producao.status == "CONSOLIDADO"
        assert len(producao.competencia) == 6
        assert producao.consolidado_em is not None

    def test_cnes_invalido_lanca_value_error(self) -> None:
        with pytest.raises(ValueError, match="CNES '' inválido"):
            ProducaoAmbulatorial(
                organizacao_id=1,
                atendimento_id=uuid4(),
                profissional_id=uuid4(),
                paciente_id=uuid4(),
                cnes="",
            )

        with pytest.raises(
            ValueError, match="inválido; esperado código numérico de até 7 dígitos"
        ):
            ProducaoAmbulatorial(
                organizacao_id=1,
                atendimento_id=uuid4(),
                profissional_id=uuid4(),
                paciente_id=uuid4(),
                cnes="12345678",
            )

    def test_conversao_para_bpa_dto(self) -> None:
        atendimento_id = uuid4()
        producao = ProducaoAmbulatorial(
            organizacao_id=1,
            atendimento_id=atendimento_id,
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="7654321",
            codigo_sigtap="03.01.01.025-0",
            carater_atendimento="02",
        )

        dto = ProducaoAmbulatorialService.converter_para_bpa_dto(producao)
        assert dto.atendimento_id == atendimento_id
        assert dto.cnes == "7654321"
        assert dto.codigo_sigtap == "03.01.01.025-0"
        assert dto.carater_atendimento == "02"
        assert dto.consolidado_em == producao.consolidado_em


class TestProducaoAmbulatorialService:
    """Validações do serviço de aplicação de consolidação ambulatorial SUS."""

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_sucesso(self) -> None:
        fake_session = FakeAsyncSession(results=[FakeResult(None)])
        service = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        cmd = ConsolidarTeleconsultaCommand(
            atendimento_id=uuid4(),
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
            codigo_sigtap="03.01.01.025-0",
            carater_atendimento="02",
        )

        dto = await service.consolidar_teleconsulta(cmd, organizacao_id=10)

        assert dto.atendimento_id == cmd.atendimento_id
        assert dto.cnes == "2000001"
        assert dto.codigo_sigtap == "03.01.01.025-0"
        assert dto.carater_atendimento == "02"
        assert fake_session.commits == 1
        assert len(fake_session.added) == 1
        assert isinstance(fake_session.added[0], ProducaoAmbulatorial)
        assert fake_session.added[0].organizacao_id == 10

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_idempotente(self) -> None:
        atendimento_id = uuid4()
        existente = ProducaoAmbulatorial(
            organizacao_id=10,
            atendimento_id=atendimento_id,
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
            codigo_sigtap="03.01.01.025-0",
            carater_atendimento="02",
        )

        fake_session = FakeAsyncSession(results=[FakeResult(existente)])
        service = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        cmd = ConsolidarTeleconsultaCommand(
            atendimento_id=atendimento_id,
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
        )

        dto = await service.consolidar_teleconsulta(cmd, organizacao_id=10)

        assert dto.atendimento_id == atendimento_id
        assert fake_session.commits == 0
        assert len(fake_session.added) == 0
