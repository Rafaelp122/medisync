"""SQL directory adapter for BPA-I export (isolated raw SQL, infra only)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.ambulatory.application.dtos import BpaRegistroDetalheDTO
from src.modules.ambulatory.application.ports.bpa_directory_port import BpaDirectoryPort


class SqlBpaDirectory(BpaDirectoryPort):
    """Raw-SQL directory adapter to fetch BPA-I details without cross-module imports."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_detalhes_bpa_lote(
        self,
        competencia: str,
    ) -> list[BpaRegistroDetalheDTO]:
        """Busca itens de produção BPA-I com valores nulos honestos da unidade SUS.

        Preserva idade == 0 (lactentes), retorna None para campos ausentes sem
        sentinelas artificiais ('20000101', CPF como CNS ou CBO fixo para eMulti).
        Regras: ADR-012, docs/explanation/domains/ambulatory-domain.md e
        docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md.
        """
        stmt = text(
            """
            SELECT
                pa.id AS producao_id,
                pa.atendimento_id,
                pa.profissional_id,
                pa.paciente_id,
                COALESCE(NULLIF(pa.cnes, '0000000'), NULLIF(TRIM(u.cnes), '')) AS cnes,
                pa.codigo_sigtap,
                pa.carater_atendimento,
                pa.competencia,
                pa.consolidado_em,
                NULLIF(TRIM(p.nome_completo), '') AS paciente_nome,
                NULLIF(TRIM(p.cns), '') AS paciente_cns,
                NULLIF(TRIM(p.cpf), '') AS paciente_cpf,
                TO_CHAR(p.data_nascimento, 'YYYYMMDD') AS paciente_data_nascimento,
                NULLIF(TRIM(p.sexo_biologico), '') AS paciente_sexo,
                NULLIF(TRIM(u.ibge_municipio), '') AS paciente_ibge,
                NULL::VARCHAR(15) AS medico_cns,
                CASE
                    WHEN ag.especialidade = 'PSICOLOGIA' THEN '251510'
                    WHEN ag.especialidade = 'NUTRICAO' THEN '223710'
                    WHEN pr.papel = 'MEDICO' THEN '225125'
                    ELSE NULL
                END AS medico_cbo,
                COALESCE(
                    NULLIF(TRIM(u.nome_fantasia), ''),
                    NULLIF(TRIM(u.razao_social), '')
                ) AS unidade_nome,
                CASE WHEN u.id IS NOT NULL THEN 'MSYNC' ELSE NULL END AS unidade_sigla,
                NULLIF(TRIM(u.cnpj), '') AS unidade_cnpj,
                NULLIF(TRIM(ec.cid10_principal), '') AS cid,
                EXTRACT(YEAR FROM AGE(pa.consolidado_em::date, p.data_nascimento))::INT
                    AS idade
            FROM producoes_ambulatoriais pa
            JOIN pacientes p ON pa.paciente_id = p.id
            JOIN profissionais pr ON pa.profissional_id = pr.id
            LEFT JOIN agendamentos ag ON ag.atendimento_id = pa.atendimento_id
            LEFT JOIN evolucoes_clinicas ec ON ec.atendimento_id = pa.atendimento_id
            LEFT JOIN (SELECT * FROM configuracoes_unidade LIMIT 1) u ON true
            WHERE pa.competencia = :competencia
            ORDER BY pa.consolidado_em ASC
            """
        )
        result = await self._session.execute(stmt, {"competencia": competencia})
        rows = result.mappings().all()

        detalhes: list[BpaRegistroDetalheDTO] = []
        for r in rows:
            raw_idade = r.get("idade")
            idade = int(raw_idade) if raw_idade is not None else None
            detalhes.append(
                BpaRegistroDetalheDTO(
                    producao_id=r["producao_id"],
                    atendimento_id=r["atendimento_id"],
                    profissional_id=r["profissional_id"],
                    paciente_id=r["paciente_id"],
                    cnes=r["cnes"],
                    codigo_sigtap=r["codigo_sigtap"],
                    carater_atendimento=r["carater_atendimento"],
                    competencia=r["competencia"],
                    consolidado_em=r["consolidado_em"],
                    paciente_nome=r["paciente_nome"],
                    paciente_cns=r["paciente_cns"],
                    paciente_cpf=r["paciente_cpf"],
                    paciente_data_nascimento=r["paciente_data_nascimento"],
                    paciente_sexo=r["paciente_sexo"],
                    paciente_ibge=r["paciente_ibge"],
                    medico_cns=r["medico_cns"],
                    medico_cbo=r["medico_cbo"],
                    unidade_nome=r["unidade_nome"],
                    unidade_sigla=r["unidade_sigla"],
                    unidade_cnpj=r["unidade_cnpj"],
                    cid=r.get("cid"),
                    idade=idade,
                )
            )
        return detalhes
