"""Unit tests for SUS ambulatory production model and service (ADR-012, US-11)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from src.core.audit import AtorPapel, AtorTipo
from src.core.errors import ValidationError
from src.modules.ambulatory.application.dtos import (
    BpaArquivoExportadoDTO,
    BpaRegistroDetalheDTO,
    ConsolidarTeleconsultaCommand,
)
from src.modules.ambulatory.application.services.producao_service import (
    ProducaoAmbulatorialService,
)
from src.modules.ambulatory.domain.exceptions import (
    CompetenciaInvalidaError,
    ProducaoNaoEncontradaError,
)
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)

from tests.doubles import (
    FakeAsyncSession,
    FakeAuditTrail,
    FakeBpaDirectory,
    FakeResult,
)


def _unique_integrity_error() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO producoes_ambulatoriais",
        {},
        SimpleNamespace(
            sqlstate="23505",
            diag=SimpleNamespace(
                constraint_name="uq_producoes_ambulatoriais_atendimento_id"
            ),
        ),  # type: ignore[arg-type]
    )


class TestProducaoAmbulatorialModel:
    """Validações do modelo rico de Produção Ambulatorial SUS."""

    def test_criar_producao_ambulatorial_sucesso(self) -> None:
        atendimento_id = uuid4()
        profissional_id = uuid4()
        paciente_id = uuid4()

        producao = ProducaoAmbulatorial(
            atendimento_id=atendimento_id,
            profissional_id=profissional_id,
            paciente_id=paciente_id,
            cnes="1234567",
        )

        assert not hasattr(producao, "organizacao_id")
        assert producao.atendimento_id == atendimento_id
        assert producao.profissional_id == profissional_id
        assert producao.paciente_id == paciente_id
        assert producao.cnes == "1234567"
        assert producao.codigo_sigtap == "03.01.01.025-0"
        assert producao.carater_atendimento == "02"
        assert producao.status == "CONSOLIDADO"
        assert len(producao.competencia) == 6
        assert producao.consolidado_em is not None

    @pytest.mark.parametrize("cnes_invalido", ["", "12345678", "ABC", "12A4567"])
    def test_cnes_invalido_lanca_validation_error(self, cnes_invalido: str) -> None:
        with pytest.raises(ValidationError, match="CNES"):
            ProducaoAmbulatorial(
                atendimento_id=uuid4(),
                profissional_id=uuid4(),
                paciente_id=uuid4(),
                cnes=cnes_invalido,
            )

    @pytest.mark.parametrize("comp_invalida", ["", "202613", "202600", "ABC"])
    def test_competencia_invalida_lanca_validation_error(
        self, comp_invalida: str
    ) -> None:
        with pytest.raises(ValidationError, match="YYYYMM"):
            ProducaoAmbulatorial(
                atendimento_id=uuid4(),
                profissional_id=uuid4(),
                paciente_id=uuid4(),
                cnes="2000001",
                competencia=comp_invalida,
            )


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

        producao = await service.consolidar_teleconsulta(cmd)

        assert isinstance(producao, ProducaoAmbulatorial)
        assert producao.atendimento_id == cmd.atendimento_id
        assert producao.cnes == "2000001"
        assert producao.codigo_sigtap == "03.01.01.025-0"
        assert producao.carater_atendimento == "02"
        assert fake_session.commits == 1
        assert fake_session.flushes == 1
        assert len(fake_session.added) == 1
        assert fake_session.added[0] is producao

        assert len(fake_audit.events) == 1
        evento = fake_audit.events[0]
        assert evento["tipo_evento"] == "PRODUCAO_AMBULATORIAL_CONSOLIDADA"
        assert "organizacao_id" not in evento
        assert evento["atendimento_id"] == cmd.atendimento_id
        assert evento["ator_tipo"] == AtorTipo.SISTEMA.value
        assert evento["ator_papel"] == AtorPapel.WORKER_ARQ.value
        assert evento["novo_estado"] == "CONSOLIDADO"
        assert evento["payload"]["cnes"] == "2000001"
        assert evento["payload"]["codigo_sigtap"] == "03.01.01.025-0"
        assert evento["payload"]["producao_id"] == str(producao.id)
        assert evento["payload"]["competencia"] == producao.competencia

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_flush_only_auto_commit_false(self) -> None:
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
        )

        producao = await service.consolidar_teleconsulta(cmd, auto_commit=False)

        assert isinstance(producao, ProducaoAmbulatorial)
        assert fake_session.commits == 0
        assert fake_session.flushes == 1
        assert len(fake_session.added) == 1
        assert len(fake_audit.events) == 1
        assert fake_audit.events[0]["ator_papel"] == AtorPapel.WORKER_ARQ.value

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_idempotente(self) -> None:
        atendimento_id = uuid4()
        existente = ProducaoAmbulatorial(
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

        res = await service.consolidar_teleconsulta(cmd)

        assert res is existente
        assert fake_session.commits == 0
        assert len(fake_session.added) == 0
        assert len(fake_audit.events) == 0

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_concorrente_23505_auto_commit_true(
        self,
    ) -> None:
        atendimento_id = uuid4()
        existente = ProducaoAmbulatorial(
            atendimento_id=atendimento_id,
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
        )
        fake_session = FakeAsyncSession(
            results=[FakeResult(None), FakeResult(existente)],
            flush_error=_unique_integrity_error(),
        )
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

        res = await service.consolidar_teleconsulta(cmd, auto_commit=True)

        assert res is existente
        assert fake_session.savepoint_rollbacks == 1
        assert fake_session.rollbacks == 1
        assert fake_session.commits == 0
        assert fake_session.added == []
        assert fake_audit.events == []

    @pytest.mark.asyncio
    async def test_consolidar_teleconsulta_concorrente_23505_auto_commit_false(
        self,
    ) -> None:
        atendimento_id = uuid4()
        existente = ProducaoAmbulatorial(
            atendimento_id=atendimento_id,
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
        )
        fake_session = FakeAsyncSession(
            results=[FakeResult(None), FakeResult(existente)],
            flush_error=_unique_integrity_error(),
        )
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

        res = await service.consolidar_teleconsulta(cmd, auto_commit=False)

        assert res is existente
        assert fake_session.savepoint_rollbacks == 1
        assert fake_session.rollbacks == 0
        assert fake_session.commits == 0
        assert fake_session.added == []
        assert fake_audit.events == []

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
            paciente_cpf="123",
            paciente_data_nascimento="",
        )

        producao = await service.consolidar_teleconsulta(cmd)

        assert producao.atendimento_id == cmd.atendimento_id
        assert fake_session.commits == 1

        tipos_eventos = [e["tipo_evento"] for e in fake_audit.events]
        assert "PRODUCAO_PENDENCIA_CADASTRAL" in tipos_eventos
        assert "PRODUCAO_AMBULATORIAL_CONSOLIDADA" in tipos_eventos
        assert all(
            e["ator_papel"] == AtorPapel.WORKER_ARQ.value for e in fake_audit.events
        )

    @pytest.mark.asyncio
    async def test_listar_producao_por_competencia_sucesso(self) -> None:
        prod1 = ProducaoAmbulatorial(
            atendimento_id=uuid4(),
            profissional_id=uuid4(),
            paciente_id=uuid4(),
            cnes="2000001",
            competencia="202611",
        )
        fake_session = FakeAsyncSession(results=[FakeResult(1), FakeResult([prod1])])
        service = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        items, total = await service.listar_producao_por_competencia(
            competencia="202611",
            page=1,
            size=10,
        )

        assert total == 1
        assert items == [prod1]

    @pytest.mark.asyncio
    async def test_listar_producao_competencia_invalida_raises(self) -> None:
        fake_session = FakeAsyncSession()
        service = ProducaoAmbulatorialService(session=fake_session)  # pyright: ignore[reportArgumentType]

        with pytest.raises(CompetenciaInvalidaError):
            await service.listar_producao_por_competencia(competencia="202613")

    @pytest.mark.asyncio
    async def test_gerar_arquivo_bpa_i_sucesso_read_only_sem_auditoria(self) -> None:
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
            paciente_cns=None,  # gera pendência real sem disparar escrita em GET
            paciente_cpf="12345678900",
            paciente_data_nascimento="20000101",
            paciente_sexo="F",
            paciente_ibge="355030",
            medico_cns="700000000000002",
            medico_cbo="225125",
            unidade_nome="UNIDADE MUNICIPAL DE SAUDE",
            unidade_sigla="MSYNC",
            unidade_cnpj="11222333000144",
            cid="R509",
            idade=26,
        )

        fake_session = FakeAsyncSession()
        fake_audit = FakeAuditTrail()
        fake_directory = FakeBpaDirectory([registro])
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            audit_trail=fake_audit,
            bpa_directory=fake_directory,
        )

        dto = await service.gerar_arquivo_bpa_i(competencia="202611")

        assert isinstance(dto, BpaArquivoExportadoDTO)
        assert dto.total_registros == 1
        assert dto.total_folhas == 1
        assert dto.competencia == "202611"
        assert dto.nome_arquivo == "BPA_I_202611_2000001.txt"
        assert dto.conteudo.startswith("01#BPA#202611")
        assert "032000001202611700000000000002" in dto.conteudo
        assert len(dto.pendencias) == 1
        assert dto.pendencias[0].campos_ausentes == ("paciente_cns",)
        assert fake_audit.events == []
        assert fake_session.commits == 0
        assert fake_session.flushes == 0
        assert fake_session.added == []

    @pytest.mark.asyncio
    async def test_gerar_arquivo_bpa_i_sem_registros_raises(self) -> None:
        fake_session = FakeAsyncSession()
        service = ProducaoAmbulatorialService(
            session=fake_session,  # pyright: ignore[reportArgumentType]
            bpa_directory=FakeBpaDirectory([]),
        )

        with pytest.raises(ProducaoNaoEncontradaError) as exc_info:
            await service.gerar_arquivo_bpa_i(competencia="202611")
        assert "202611" in str(exc_info.value)


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
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes="7654321",
        )

        assert fake_session.commits == 0
        assert fake_session.flushes == 1
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
                medico_id: object,
                atendimento_id: object,
            ) -> DadosVerificacaoDirectory:
                return self._dados

        fake_dados = DadosVerificacaoDirectory(
            organizacao_nome="Unidade SUS",
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
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes=None,
        )

        assert fake_session.commits == 0
        assert fake_session.flushes == 1
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
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes=None,
        )

        assert fake_session.commits == 0
        assert fake_session.flushes == 1
        assert len(fake_session.added) == 1
        assert fake_session.added[0].cnes == "0000000"


@pytest.mark.asyncio
async def test_sql_bpa_directory_preserva_nulos_honestos_e_idade_zero() -> None:
    """SqlBpaDirectory preserva idade == 0, None honesto, sem sentinelas ou CPF/CNS."""
    from src.modules.ambulatory.infrastructure.adapters.sql_bpa_directory import (
        SqlBpaDirectory,
    )

    row_lactente = {
        "producao_id": uuid4(),
        "atendimento_id": uuid4(),
        "profissional_id": uuid4(),
        "paciente_id": uuid4(),
        "cnes": "2695251",
        "codigo_sigtap": "03.01.01.025-0",
        "carater_atendimento": "02",
        "competencia": "202611",
        "consolidado_em": datetime.now(UTC),
        "paciente_nome": "BEBE DA SILVA",
        "paciente_cns": None,
        "paciente_cpf": "12345678900",
        "paciente_data_nascimento": "20260615",
        "paciente_sexo": None,
        "paciente_ibge": None,
        "medico_cns": None,
        "medico_cbo": "251510",
        "unidade_nome": "UPA DIGITAL UNICA",
        "unidade_sigla": "MSYNC",
        "unidade_cnpj": "12345678000199",
        "cid": None,
        "idade": 0,
    }
    fake_session = FakeAsyncSession(results=[FakeResult(mappings_rows=[row_lactente])])
    directory = SqlBpaDirectory(session=fake_session)  # pyright: ignore[reportArgumentType]
    rows = await directory.buscar_detalhes_bpa_lote("202611")

    assert len(rows) == 1
    assert rows[0].idade == 0
    assert rows[0].paciente_cns is None
    assert rows[0].paciente_sexo is None
    assert rows[0].paciente_ibge is None
    assert rows[0].medico_cns is None
    assert rows[0].medico_cbo == "251510"
    assert rows[0].unidade_nome == "UPA DIGITAL UNICA"
    assert rows[0].unidade_cnpj == "12345678000199"
    assert rows[0].cnes == "2695251"

    sql_str, params = fake_session.executed_sql[0]
    assert "configuracoes_unidade" in sql_str
    assert "agendamentos" in sql_str
    assert "PSICOLOGIA" in sql_str
    assert "NUTRICAO" in sql_str
    assert "organizacoes" not in sql_str
    assert "organizacao_id" not in sql_str
    assert "20000101" not in sql_str
    assert "pr.cpf" not in sql_str
    assert "COALESCE(p.cns, p.cpf" not in sql_str
    assert params == {"competencia": "202611"}
