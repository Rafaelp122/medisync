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

from tests.doubles import FakeAsyncSession, FakeAuditTrail, FakeResult


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
        fake_audit = FakeAuditTrail()
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            audit_trail=fake_audit,
        )

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

        # Validação do evento de auditoria append-only (ADR-007, ADR-012)
        assert len(fake_audit.events) == 1
        evento = fake_audit.events[0]
        assert evento["tipo_evento"] == "PRODUCAO_AMBULATORIAL_CONSOLIDADA"
        assert evento["organizacao_id"] == 10
        assert evento["atendimento_id"] == cmd.atendimento_id
        assert evento["ator_tipo"] == "SISTEMA"
        assert evento["ator_papel"] == "WORKER"
        assert evento["novo_estado"] == "CONSOLIDADO"
        assert evento["payload"]["cnes"] == "2000001"
        assert evento["payload"]["codigo_sigtap"] == "03.01.01.025-0"
        assert evento["payload"]["producao_id"] == str(fake_session.added[0].id)
        assert evento["payload"]["competencia"] == fake_session.added[0].competencia

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
        fake_audit = FakeAuditTrail()
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            audit_trail=fake_audit,
        )

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
        assert len(fake_audit.events) == 0

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_com_pendencia_cadastral(self) -> None:
        fake_session = FakeAsyncSession(results=[FakeResult(None)])
        fake_audit = FakeAuditTrail()
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            audit_trail=fake_audit,
        )

        cmd = ConsolidarTeleconsultaCommand(
            atendimento_id=uuid4(),
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
            codigo_sigtap="03.01.01.025-0",
            carater_atendimento="02",
            paciente_cns="",
            paciente_cpf="123",  # incompleto
            paciente_data_nascimento="",  # ausente
        )

        dto = await service.consolidar_teleconsulta(cmd, organizacao_id=10)

        assert dto.atendimento_id == cmd.atendimento_id
        assert fake_session.commits == 1

        # Auditoria deve registrar pendência cadastral sem bloquear
        # a consolidação (US-11 Cenário 2)
        tipos_eventos = [e["tipo_evento"] for e in fake_audit.events]
        assert "PRODUCAO_PENDENCIA_CADASTRAL" in tipos_eventos
        assert "PRODUCAO_AMBULATORIAL_CONSOLIDADA" in tipos_eventos

    @pytest.mark.asyncio
    async def test_listar_producao_por_competencia_sucesso(self) -> None:
        from src.modules.ambulatory.application.dtos import ListaProducaoAmbulatorialDTO

        prod1 = ProducaoAmbulatorial(
            organizacao_id=10,
            atendimento_id=uuid4(),
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
            competencia="202611",
        )
        fake_session = FakeAsyncSession(results=[FakeResult(1), FakeResult([prod1])])
        service = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        res = await service.listar_producao_por_competencia(
            organizacao_id=10,
            competencia="202611",
            page=1,
            size=10,
        )

        assert isinstance(res, ListaProducaoAmbulatorialDTO)
        assert res.total == 1
        assert len(res.items) == 1
        assert res.items[0].atendimento_id == prod1.atendimento_id
        assert res.competencia == "202611"
        assert res.organizacao_id == 10

    @pytest.mark.asyncio
    async def test_listar_producao_competencia_invalida_raises(self) -> None:
        from src.modules.ambulatory.domain.exceptions import CompetenciaInvalidaError

        fake_session = FakeAsyncSession()
        service = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        with pytest.raises(CompetenciaInvalidaError):
            await service.listar_producao_por_competencia(
                organizacao_id=10,
                competencia="202613",
            )

    @pytest.mark.asyncio
    async def test_gerar_arquivo_bpa_i_sucesso(self) -> None:
        from datetime import UTC, datetime

        from src.modules.ambulatory.application.dtos import (
            BpaArquivoExportadoDTO,
            BpaRegistroDetalheDTO,
        )

        registro = BpaRegistroDetalheDTO(
            producao_id=uuid4(),
            atendimento_id=uuid4(),
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
            codigo_sigtap="03.01.01.025-0",
            carater_atendimento="02",
            competencia="202611",
            consolidado_em=datetime.now(UTC),
            paciente_nome="MARIA DA SILVA",
            paciente_cns="700000000000001",
            paciente_cpf="12345678900",
            paciente_data_nascimento="19850412",
            paciente_sexo="F",
            paciente_ibge="355030",
            medico_cns="700000000000002",
            medico_cbo="225125",
            org_nome="CONSÓRCIO INTERMUNICIPAL SAÚDE",
            org_sigla="CIS",
            org_cnpj="11222333000144",
            cid="R509",
            idade=41,
        )

        class FakeDirectory:
            async def buscar_detalhes_bpa_lote(
                self, organizacao_id: int, competencia: str
            ) -> list[BpaRegistroDetalheDTO]:
                return [registro]

        fake_session = FakeAsyncSession()
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            bpa_directory=FakeDirectory(),  # pyright: ignore[reportArgumentType]
        )

        dto = await service.gerar_arquivo_bpa_i(
            organizacao_id=10,
            competencia="202611",
        )

        assert isinstance(dto, BpaArquivoExportadoDTO)
        assert dto.total_registros == 1
        assert dto.total_folhas == 1
        assert dto.competencia == "202611"
        assert dto.nome_arquivo == "BPA_I_202611_2000001.txt"
        assert dto.conteudo.startswith("01#BPA#202611")
        assert "032000001202611700000000000002" in dto.conteudo

    @pytest.mark.asyncio
    async def test_gerar_arquivo_bpa_i_sem_registros_raises(self) -> None:
        from src.modules.ambulatory.application.dtos import (
            BpaRegistroDetalheDTO,
        )
        from src.modules.ambulatory.domain.exceptions import ProducaoNaoEncontradaError

        class FakeEmptyDirectory:
            async def buscar_detalhes_bpa_lote(
                self, organizacao_id: int, competencia: str
            ) -> list[BpaRegistroDetalheDTO]:
                return []

        fake_session = FakeAsyncSession()
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            bpa_directory=FakeEmptyDirectory(),  # pyright: ignore[reportArgumentType]
        )

        with pytest.raises(ProducaoNaoEncontradaError) as exc_info:
            await service.gerar_arquivo_bpa_i(
                organizacao_id=10,
                competencia="202611",
            )
        assert "202611" in str(exc_info.value)
        assert "10" in str(exc_info.value)


class TestAmbulatoryProducaoAdapter:
    """Validações do adapter AmbulatoryProducaoAdapter (ADR-012)."""

    @pytest.mark.asyncio
    async def test_adapter_repassa_cnes_explicitamente(self) -> None:
        from src.modules.consultation.composition import AmbulatoryProducaoAdapter

        fake_session = FakeAsyncSession(results=[FakeResult(None)])
        prod_svc = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]
        adapter = AmbulatoryProducaoAdapter(producao_service=prod_svc)

        atend_id = uuid4()
        med_id = uuid4()
        pac_id = uuid4()

        await adapter.consolidar_teleconsulta(
            organizacao_id=1,
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes="7654321",
        )

        assert fake_session.commits == 1
        assert len(fake_session.added) == 1
        assert fake_session.added[0].cnes == "7654321"

    @pytest.mark.asyncio
    async def test_adapter_obtem_cnes_do_diretorio(self) -> None:
        from src.modules.consultation.application.ports.document_directory_port import (
            DadosVerificacaoDirectory,
            DocumentDirectoryPort,
        )
        from src.modules.consultation.composition import AmbulatoryProducaoAdapter

        fake_session = FakeAsyncSession(results=[FakeResult(None)])
        prod_svc = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        class FakeDocumentDirectory(DocumentDirectoryPort):
            def __init__(self, dados: DadosVerificacaoDirectory) -> None:
                self._dados = dados

            async def obter_dados_verificacao(
                self,
                organizacao_id: int,
                medico_id: object,
                atendimento_id: object,
            ) -> DadosVerificacaoDirectory:
                return self._dados

        fake_dados = DadosVerificacaoDirectory(
            organizacao_nome="Org SUS",
            medico_nome="Dr. Medico",
            medico_crm="12345",
            medico_crm_uf="SP",
            paciente_nome="Paciente",
            paciente_cpf="111.111.111-11",
            cnes="3333333",
        )
        fake_dir = FakeDocumentDirectory(fake_dados)

        adapter = AmbulatoryProducaoAdapter(
            producao_service=prod_svc, directory=fake_dir
        )

        atend_id = uuid4()
        med_id = uuid4()
        pac_id = uuid4()

        await adapter.consolidar_teleconsulta(
            organizacao_id=1,
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes=None,
        )

        assert fake_session.commits == 1
        assert len(fake_session.added) == 1
        assert fake_session.added[0].cnes == "3333333"

    @pytest.mark.asyncio
    async def test_adapter_usa_fallback_quando_diretorio_indisponivel(self) -> None:
        from src.modules.consultation.composition import AmbulatoryProducaoAdapter

        fake_session = FakeAsyncSession(results=[FakeResult(None)])
        prod_svc = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]
        adapter = AmbulatoryProducaoAdapter(producao_service=prod_svc, directory=None)

        atend_id = uuid4()
        med_id = uuid4()
        pac_id = uuid4()

        await adapter.consolidar_teleconsulta(
            organizacao_id=1,
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes=None,
        )

        assert fake_session.commits == 1
        assert len(fake_session.added) == 1
        assert fake_session.added[0].cnes == "0000000"
