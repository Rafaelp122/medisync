"""Initial database schema with UUIDv7, clinical domain tables, and audit trigger.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Habilitação de extensões PostgreSQL
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # 2. Função utilitária para geração nativa de UUIDv7 no PostgreSQL 17 (RFC 9562)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION gen_uuidv7()
        RETURNS UUID AS $$
        DECLARE
            v_time TIMESTAMP WITH TIME ZONE := clock_timestamp();
            v_unix_time_ms BIGINT;
            v_rand BYTEA;
            v_hex VARCHAR;
        BEGIN
            v_unix_time_ms := FLOOR(EXTRACT(EPOCH FROM v_time) * 1000)::BIGINT;
            v_rand := gen_random_bytes(10);
            v_hex := LPAD(TO_HEX(v_unix_time_ms), 12, '0') ||
                     '7' || SUBSTRING(ENCODE(v_rand, 'hex') FROM 2 FOR 3) ||
                     '8' || SUBSTRING(ENCODE(v_rand, 'hex') FROM 5 FOR 3) ||
                     SUBSTRING(ENCODE(v_rand, 'hex') FROM 8 FOR 12);
            RETURN v_hex::UUID;
        END;
        $$ LANGUAGE plpgsql VOLATILE;
        """
    )

    # 3. Tabela de Organizações (Tenants)
    op.create_table(
        "organizacoes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cnpj", sa.String(length=18), nullable=False),
        sa.Column("razao_social", sa.String(length=255), nullable=False),
        sa.Column("nome_fantasia", sa.String(length=255), nullable=False),
        sa.Column(
            "modo_publico_sus",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "config_plantao",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                '\'{"alpha_margem": 1.25, "tma_estimado_segundos": 600, '
                '"cota_diaria_maxima": 300}\'::jsonb'
            ),
            nullable=False,
        ),
        sa.Column(
            "ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizacoes"),
        sa.UniqueConstraint("cnpj", name="uq_organizacoes_cnpj"),
    )

    # 4. Tabela de Profissionais
    op.create_table(
        "profissionais",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("cpf", sa.String(length=14), nullable=False),
        sa.Column("nome_completo", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("papel", sa.String(length=32), nullable=False),
        sa.Column("crm", sa.String(length=20), nullable=True),
        sa.Column("crm_uf", sa.String(length=2), nullable=True),
        sa.Column(
            "ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_profissionais_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profissionais"),
        sa.UniqueConstraint(
            "organizacao_id", "email", name="uq_profissional_org_email"
        ),
        sa.UniqueConstraint("organizacao_id", "cpf", name="uq_profissional_org_cpf"),
    )
    op.create_index(
        "idx_profissionais_org_papel",
        "profissionais",
        ["organizacao_id", "papel"],
    )

    # 5. Tabela de Pacientes
    op.create_table(
        "pacientes",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("cpf", sa.String(length=14), nullable=True),
        sa.Column("cns", sa.String(length=15), nullable=True),
        sa.Column("data_nascimento", sa.Date(), nullable=False),
        sa.Column("nome_completo", sa.String(length=255), nullable=True),
        sa.Column("nome_mae", sa.String(length=255), nullable=True),
        sa.Column("sexo_biologico", sa.String(length=1), nullable=True),
        sa.Column("telefone", sa.String(length=20), nullable=False),
        sa.Column("cep", sa.String(length=9), nullable=True),
        sa.Column("logradouro", sa.String(length=255), nullable=True),
        sa.Column("numero", sa.String(length=20), nullable=True),
        sa.Column("bairro", sa.String(length=100), nullable=True),
        sa.Column("cidade", sa.String(length=100), nullable=True),
        sa.Column("estado", sa.String(length=2), nullable=True),
        sa.Column(
            "alergias",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_pacientes_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pacientes"),
        sa.CheckConstraint(
            "cpf IS NOT NULL OR cns IS NOT NULL",
            name="chk_documento_paciente_obrigatorio",
        ),
    )
    op.create_index(
        "uq_paciente_org_cpf",
        "pacientes",
        ["organizacao_id", "cpf"],
        unique=True,
        postgresql_where=sa.text("cpf IS NOT NULL"),
    )
    op.create_index(
        "uq_paciente_org_cns",
        "pacientes",
        ["organizacao_id", "cns"],
        unique=True,
        postgresql_where=sa.text("cns IS NOT NULL"),
    )
    op.create_index(
        "idx_pacientes_org_telefone",
        "pacientes",
        ["organizacao_id", "telefone"],
    )

    # 6. Tabela de Dependentes
    op.create_table(
        "dependentes",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("titular_id", sa.UUID(), nullable=False),
        sa.Column("dependente_id", sa.UUID(), nullable=False),
        sa.Column("grau_parentesco", sa.String(length=32), nullable=False),
        sa.Column(
            "vinculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_dependentes_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["titular_id"],
            ["pacientes.id"],
            name="fk_dependentes_titular_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dependente_id"],
            ["pacientes.id"],
            name="fk_dependentes_dependente_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dependentes"),
        sa.UniqueConstraint(
            "titular_id", "dependente_id", name="uq_dependente_vinculo"
        ),
    )
    op.create_index(
        "idx_dependentes_org",
        "dependentes",
        ["organizacao_id"],
    )

    # 7. Tabela de Atendimentos
    op.create_table(
        "atendimentos",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("medico_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="TRIADO_AGUARDANDO_ELEGIBILIDADE",
            nullable=False,
        ),
        sa.Column(
            "prioridade_clinica",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column("tcle_hash", sa.String(length=64), nullable=True),
        sa.Column("data_entrada_fila", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chamada_iniciada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chamada_finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_atendimentos_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name="fk_atendimentos_paciente_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["medico_id"],
            ["profissionais.id"],
            name="fk_atendimentos_medico_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_atendimentos"),
        sa.CheckConstraint(
            "status IN ('TRIADO_AGUARDANDO_ELEGIBILIDADE', 'APTO_PARA_CHAMADA', "
            "'CHAMANDO_PACIENTE', 'EM_ATENDIMENTO', 'PACIENTE_AUSENTE', "
            "'CONCLUIDO', 'CANCELADO_PACIENTE')",
            name="chk_atendimento_status",
        ),
        sa.CheckConstraint(
            "prioridade_clinica >= 1 AND prioridade_clinica <= 5",
            name="chk_atendimento_prioridade",
        ),
    )
    op.create_index(
        "idx_atendimentos_org_status",
        "atendimentos",
        ["organizacao_id", "status"],
    )
    op.create_index(
        "idx_atendimentos_fila",
        "atendimentos",
        [
            "organizacao_id",
            "status",
            "prioridade_clinica",
            "data_entrada_fila",
        ],
    )

    # 8. Tabela de Triagens
    op.create_table(
        "triagens",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("queixa_principal", sa.Text(), nullable=False),
        sa.Column(
            "sintomas_alerta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "alerta_samu_disparado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("prioridade_calculada", sa.Integer(), nullable=False),
        sa.Column(
            "avaliado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_triagens_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_triagens_atendimento_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_triagens"),
        sa.UniqueConstraint("atendimento_id", name="uq_triagens_atendimento_id"),
        sa.CheckConstraint(
            "prioridade_calculada >= 1 AND prioridade_calculada <= 5",
            name="chk_triagem_prioridade",
        ),
    )
    op.create_index(
        "idx_triagens_org",
        "triagens",
        ["organizacao_id"],
    )

    # 9. Tabela de Evoluções Clínicas
    op.create_table(
        "evolucoes_clinicas",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("medico_id", sa.UUID(), nullable=False),
        sa.Column("anamnese", sa.Text(), nullable=False),
        sa.Column("exame_fisico_virtual", sa.Text(), nullable=True),
        sa.Column("cid10_principal", sa.String(length=10), nullable=True),
        sa.Column("conduta", sa.Text(), nullable=False),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_evolucoes_clinicas_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_evolucoes_clinicas_atendimento_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["medico_id"],
            ["profissionais.id"],
            name="fk_evolucoes_clinicas_medico_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evolucoes_clinicas"),
    )
    op.create_index(
        "idx_evolucoes_atendimento",
        "evolucoes_clinicas",
        ["atendimento_id"],
    )
    op.create_index(
        "idx_evolucoes_org",
        "evolucoes_clinicas",
        ["organizacao_id"],
    )

    # 10. Tabela de Documentos Clínicos
    op.create_table(
        "documentos_clinicos",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("medico_id", sa.UUID(), nullable=False),
        sa.Column("tipo_documento", sa.String(length=32), nullable=False),
        sa.Column("chave_s3", sa.String(length=512), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "assinado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_documentos_clinicos_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_documentos_clinicos_atendimento_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["medico_id"],
            ["profissionais.id"],
            name="fk_documentos_clinicos_medico_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documentos_clinicos"),
        sa.CheckConstraint(
            "tipo_documento IN ('RECEITA_SIMPLES', 'RECEITA_ANTIMICROBIANO', "
            "'RECEITA_CONTROLE_ESPECIAL_C1', 'ATESTADO_MEDICO', "
            "'RELATORIO_ENCAMINHAMENTO')",
            name="chk_documentos_tipo",
        ),
        sa.CheckConstraint(
            "length(sha256_hash) = 64",
            name="chk_documentos_sha256_len",
        ),
    )
    op.create_index(
        "idx_documentos_atendimento",
        "documentos_clinicos",
        ["atendimento_id"],
    )
    op.create_index(
        "idx_documentos_org",
        "documentos_clinicos",
        ["organizacao_id"],
    )

    # 11. Tabela de Itens de Prescrição
    op.create_table(
        "documento_itens",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("documento_id", sa.UUID(), nullable=False),
        sa.Column("medicamento", sa.String(length=255), nullable=False),
        sa.Column("dosagem", sa.String(length=100), nullable=False),
        sa.Column("posologia", sa.Text(), nullable=False),
        sa.Column("duracao", sa.String(length=50), nullable=True),
        sa.Column(
            "controle_especial",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_documento_itens_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"],
            ["documentos_clinicos.id"],
            name="fk_documento_itens_documento_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documento_itens"),
    )
    op.create_index(
        "idx_documento_itens_doc",
        "documento_itens",
        ["documento_id"],
    )
    op.create_index(
        "idx_documento_itens_org",
        "documento_itens",
        ["organizacao_id"],
    )

    # 12. Tabela de Auditoria Imutável (Append-Only)
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("ator_tipo", sa.String(length=20), nullable=False),
        sa.Column("ator_id", sa.UUID(), nullable=True),
        sa.Column("ator_papel", sa.String(length=32), nullable=False),
        sa.Column("tipo_evento", sa.String(length=64), nullable=False),
        sa.Column("estado_anterior", sa.String(length=32), nullable=True),
        sa.Column("novo_estado", sa.String(length=32), nullable=True),
        sa.Column("tcle_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip_origem", postgresql.INET(), nullable=True),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_audit_events_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_audit_events_atendimento_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.CheckConstraint(
            "ator_tipo IN ('PROFISSIONAL', 'PACIENTE', 'SISTEMA')",
            name="chk_audit_ator_tipo",
        ),
    )
    op.create_index(
        "idx_audit_atendimento",
        "audit_events",
        ["atendimento_id", "registrado_em"],
    )
    op.create_index(
        "idx_audit_ator",
        "audit_events",
        ["organizacao_id", "ator_tipo", "ator_id"],
    )

    # 13. Trigger anti-adulteração de auditoria (ADR-007)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_prevent_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'A tabela audit_events é estritamente append-only '
                '(CFM 2.314/2022 e LGPD Art. 11). Operações de UPDATE ou '
                'DELETE são terminantemente proibidas.'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;
        CREATE TRIGGER trg_audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION trg_prevent_audit_mutation();
        """
    )


def downgrade() -> None:
    # 1. Remover trigger e função anti-adulteração de auditoria
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS trg_prevent_audit_mutation();")

    # 2. Excluir as 10 tabelas clínicas em ordem reversa de dependência
    op.drop_table("audit_events", if_exists=True)
    op.drop_table("documento_itens", if_exists=True)
    op.drop_table("documentos_clinicos", if_exists=True)
    op.drop_table("evolucoes_clinicas", if_exists=True)
    op.drop_table("triagens", if_exists=True)
    op.drop_table("atendimentos", if_exists=True)
    op.drop_table("dependentes", if_exists=True)
    op.drop_table("pacientes", if_exists=True)
    op.drop_table("profissionais", if_exists=True)
    op.drop_table("organizacoes", if_exists=True)

    # 3. Remover função gen_uuidv7
    op.execute("DROP FUNCTION IF EXISTS gen_uuidv7();")
