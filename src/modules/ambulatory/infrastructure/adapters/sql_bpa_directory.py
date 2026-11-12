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
        organizacao_id: int,
        competencia: str,
    ) -> list[BpaRegistroDetalheDTO]:
        """Fetch all individual production items with patient and doctor details."""
        stmt = text(
            """
            SELECT
                pa.id AS producao_id,
                pa.atendimento_id,
                pa.profissional_id,
                pa.paciente_id,
                COALESCE(NULLIF(pa.cnes, '0000000'), o.cnes, '0000000') AS cnes,
                pa.codigo_sigtap,
                pa.carater_atendimento,
                pa.competencia,
                pa.consolidado_em,
                COALESCE(p.nome_completo, 'PACIENTE NAO IDENTIFICADO') AS paciente_nome,
                COALESCE(p.cns, p.cpf, '') AS paciente_cns,
                p.cpf AS paciente_cpf,
                TO_CHAR(p.data_nascimento, 'YYYYMMDD') AS paciente_data_nascimento,
                COALESCE(p.sexo_biologico, 'M') AS paciente_sexo,
                COALESCE(o.ibge_municipio, '355030') AS paciente_ibge,
                COALESCE(pr.cpf, '000000000000000') AS medico_cns,
                '225125' AS medico_cbo,
                COALESCE(o.nome_fantasia, o.razao_social, 'UPA DIGITAL') AS org_nome,
                'MSYNC' AS org_sigla,
                COALESCE(o.cnpj, '00000000000000') AS org_cnpj,
                COALESCE(EXTRACT(YEAR FROM AGE(p.data_nascimento))::INT, 0) AS idade
            FROM producoes_ambulatoriais pa
            JOIN pacientes p ON pa.paciente_id = p.id
            JOIN profissionais pr ON pa.profissional_id = pr.id
            JOIN organizacoes o ON pa.organizacao_id = o.id
            WHERE pa.organizacao_id = :org_id
              AND pa.competencia = :competencia
            ORDER BY pa.consolidado_em ASC
            """
        )
        result = await self._session.execute(
            stmt, {"org_id": organizacao_id, "competencia": competencia}
        )
        rows = result.mappings().all()

        detalhes: list[BpaRegistroDetalheDTO] = []
        for r in rows:
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
                    paciente_cns=r["paciente_cns"] or "000000000000000",
                    paciente_cpf=r["paciente_cpf"],
                    paciente_data_nascimento=r["paciente_data_nascimento"]
                    or "20000101",
                    paciente_sexo=r["paciente_sexo"],
                    paciente_ibge=r["paciente_ibge"],
                    medico_cns=r["medico_cns"],
                    medico_cbo=r["medico_cbo"],
                    org_nome=r["org_nome"],
                    org_sigla=r["org_sigla"],
                    org_cnpj=r["org_cnpj"],
                    cid="",
                    idade=r["idade"] or 30,
                )
            )
        return detalhes
