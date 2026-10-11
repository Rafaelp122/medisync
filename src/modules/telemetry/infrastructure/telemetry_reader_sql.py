"""SQL reader: attendance aggregations and doctor TMA metrics."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.telemetry.application.dtos import MedicoTMADTO, PainelTelemetriaDTO
from src.modules.telemetry.application.ports.telemetry_reader_port import (
    TelemetryReaderPort,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


class SqlTelemetryReader(TelemetryReaderPort):
    """Encapsulates SQL aggregations over atendimentos and profissionais tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_painel_telemetria(
        self,
        organizacao_id: int,
        config: ConfiguracaoPlantao | None = None,
        data_inicio: datetime | None = None,
    ) -> PainelTelemetriaDTO:
        dt_inicio = (
            data_inicio
            if data_inicio is not None
            else datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        )

        sla_1 = (config.sla_minutos_nivel_1 * 60) if config is not None else 0
        sla_2 = (config.sla_minutos_nivel_2 * 60) if config is not None else 600
        sla_3 = (config.sla_minutos_nivel_3 * 60) if config is not None else 3600
        sla_4 = (config.sla_minutos_nivel_4 * 60) if config is not None else 7200
        sla_5 = (config.sla_minutos_nivel_5 * 60) if config is not None else 14400

        query_agregados = text(
            """
            SELECT
                COUNT(*) AS total_atendimentos,
                COUNT(*) FILTER (
                    WHERE status = 'PACIENTE_AUSENTE'
                ) AS total_ausentes,
                COUNT(*) FILTER (
                    WHERE status = 'CANCELADO_PACIENTE'
                ) AS total_cancelados,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (chamada_iniciada_em - data_entrada_fila))
                ) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                ), 0.0) AS tme_medio,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (chamada_iniciada_em - data_entrada_fila))
                ) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                      AND prioridade_clinica = 1
                ), 0.0) AS tme_nivel_1,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (chamada_iniciada_em - data_entrada_fila))
                ) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                      AND prioridade_clinica = 2
                ), 0.0) AS tme_nivel_2,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (chamada_iniciada_em - data_entrada_fila))
                ) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                      AND prioridade_clinica = 3
                ), 0.0) AS tme_nivel_3,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (chamada_iniciada_em - data_entrada_fila))
                ) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                      AND prioridade_clinica = 4
                ), 0.0) AS tme_nivel_4,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (chamada_iniciada_em - data_entrada_fila))
                ) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                      AND prioridade_clinica = 5
                ), 0.0) AS tme_nivel_5,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (
                        chamada_finalizada_em - chamada_iniciada_em
                    ))
                ) FILTER (
                    WHERE status = 'CONCLUIDO'
                      AND chamada_finalizada_em IS NOT NULL
                      AND chamada_iniciada_em IS NOT NULL
                ), 0.0) AS tma_medio,
                COUNT(*) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                ) AS total_chamados,
                COUNT(*) FILTER (
                    WHERE chamada_iniciada_em IS NOT NULL
                      AND data_entrada_fila IS NOT NULL
                      AND EXTRACT(EPOCH FROM (
                          chamada_iniciada_em - data_entrada_fila
                      )) <= (
                          CASE prioridade_clinica
                              WHEN 1 THEN :sla_1
                              WHEN 2 THEN :sla_2
                              WHEN 3 THEN :sla_3
                              WHEN 4 THEN :sla_4
                              WHEN 5 THEN :sla_5
                              ELSE 14400
                          END
                      )
                ) AS total_dentro_sla
            FROM atendimentos
            WHERE organizacao_id = :org_id
              AND criado_em >= :data_inicio
            """
        )

        res = await self._session.execute(
            query_agregados,
            {
                "org_id": organizacao_id,
                "data_inicio": dt_inicio,
                "sla_1": sla_1,
                "sla_2": sla_2,
                "sla_3": sla_3,
                "sla_4": sla_4,
                "sla_5": sla_5,
            },
        )
        row = res.mappings().one_or_none()

        total_atendimentos = int(row["total_atendimentos"]) if row is not None else 0
        total_ausentes = int(row["total_ausentes"]) if row is not None else 0
        total_cancelados = int(row["total_cancelados"]) if row is not None else 0
        total_chamados = int(row["total_chamados"]) if row is not None else 0
        total_dentro_sla = int(row["total_dentro_sla"]) if row is not None else 0

        tme_medio = float(row["tme_medio"]) if row is not None else 0.0
        tme_nivel_1 = float(row["tme_nivel_1"]) if row is not None else 0.0
        tme_nivel_2 = float(row["tme_nivel_2"]) if row is not None else 0.0
        tme_nivel_3 = float(row["tme_nivel_3"]) if row is not None else 0.0
        tme_nivel_4 = float(row["tme_nivel_4"]) if row is not None else 0.0
        tme_nivel_5 = float(row["tme_nivel_5"]) if row is not None else 0.0
        tma_medio = float(row["tma_medio"]) if row is not None else 0.0

        no_show_rate = (
            round((total_ausentes / total_atendimentos) * 100.0, 2)
            if total_atendimentos > 0
            else 0.0
        )
        evasao_rate = (
            round((total_cancelados / total_atendimentos) * 100.0, 2)
            if total_atendimentos > 0
            else 0.0
        )
        sla_compliance = (
            round((total_dentro_sla / total_chamados) * 100.0, 2)
            if total_chamados > 0
            else 100.0
        )
        sla_conforme = sla_compliance >= 95.0

        # Concurrent metrics
        medicos_tma = await self.obter_tma_por_medico(organizacao_id, dt_inicio)
        total_fila = await self.obter_contagem_fila(organizacao_id)
        medicos_ativos = await self.obter_medicos_ativos_count(
            organizacao_id, dt_inicio
        )

        return PainelTelemetriaDTO(
            organizacao_id=organizacao_id,
            gerado_em=datetime.now(UTC),
            tme_medio_segundos=round(tme_medio, 2),
            tme_nivel_1_segundos=round(tme_nivel_1, 2),
            tme_nivel_2_segundos=round(tme_nivel_2, 2),
            tme_nivel_3_segundos=round(tme_nivel_3, 2),
            tme_nivel_4_segundos=round(tme_nivel_4, 2),
            tme_nivel_5_segundos=round(tme_nivel_5, 2),
            tma_medio_segundos=round(tma_medio, 2),
            medicos_tma=medicos_tma,
            no_show_rate=no_show_rate,
            evasao_rate=evasao_rate,
            sla_compliance_percentual=sla_compliance,
            sla_em_conformidade=sla_conforme,
            medicos_ativos_count=medicos_ativos,
            total_pacientes_fila=total_fila,
            total_atendimentos=total_atendimentos,
        )

    async def obter_tma_por_medico(
        self,
        organizacao_id: int,
        data_inicio: datetime | None = None,
    ) -> tuple[MedicoTMADTO, ...]:
        dt_inicio = (
            data_inicio
            if data_inicio is not None
            else datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        )

        query = text(
            """
            SELECT
                a.medico_id,
                COALESCE(p.nome_completo, 'Profissional Médico') AS nome,
                COUNT(a.id) AS total_atendimentos,
                COALESCE(AVG(
                    EXTRACT(
                        EPOCH FROM (
                            a.chamada_finalizada_em - a.chamada_iniciada_em
                        )
                    )
                ), 0.0) AS tma_segundos
            FROM atendimentos a
            LEFT JOIN profissionais p ON a.medico_id = p.id
            WHERE a.organizacao_id = :org_id
              AND a.medico_id IS NOT NULL
              AND a.chamada_iniciada_em IS NOT NULL
              AND a.chamada_finalizada_em IS NOT NULL
              AND a.status = 'CONCLUIDO'
              AND a.criado_em >= :data_inicio
            GROUP BY a.medico_id, p.nome_completo
            ORDER BY total_atendimentos DESC, tma_segundos ASC
            """
        )

        res = await self._session.execute(
            query,
            {"org_id": organizacao_id, "data_inicio": dt_inicio},
        )
        rows = res.mappings().all()

        resultado: list[MedicoTMADTO] = []
        for r in rows:
            raw_id = r["medico_id"]
            med_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
            resultado.append(
                MedicoTMADTO(
                    medico_id=med_id,
                    nome=str(r["nome"]),
                    total_atendimentos=int(r["total_atendimentos"]),
                    tma_segundos=round(float(r["tma_segundos"]), 2),
                )
            )

        return tuple(resultado)

    async def obter_contagem_fila(
        self,
        organizacao_id: int,
    ) -> int:
        query = text(
            """
            SELECT COUNT(*) AS total_fila
            FROM atendimentos
            WHERE organizacao_id = :org_id
              AND status IN ('APTO_PARA_CHAMADA', 'CHAMANDO_PACIENTE')
            """
        )
        res = await self._session.execute(query, {"org_id": organizacao_id})
        count_val = res.scalar()
        return int(count_val) if count_val is not None else 0

    async def obter_medicos_ativos_count(
        self,
        organizacao_id: int,
        data_inicio: datetime | None = None,
    ) -> int:
        dt_inicio = (
            data_inicio
            if data_inicio is not None
            else datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        )
        query = text(
            """
            SELECT COUNT(DISTINCT medico_id) AS medicos_ativos
            FROM atendimentos
            WHERE organizacao_id = :org_id
              AND medico_id IS NOT NULL
              AND (status = 'EM_ATENDIMENTO' OR chamada_iniciada_em >= :data_inicio)
            """
        )
        res = await self._session.execute(
            query,
            {"org_id": organizacao_id, "data_inicio": dt_inicio},
        )
        count_val = res.scalar()
        return int(count_val) if count_val is not None else 0
