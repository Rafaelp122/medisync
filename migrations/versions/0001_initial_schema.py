"""Consolidated single-platform initial schema (UUIDv7, clinical tables, GiST & audit).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-20 00:00:00.000000

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
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gist"')

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

    # 3. Tabela Singleton de Configuração da Unidade de Saúde
    op.create_table(
        "configuracoes_unidade",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "singleton_guard",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("cnpj", sa.String(length=18), nullable=False),
        sa.Column("razao_social", sa.String(length=255), nullable=False),
        sa.Column("nome_fantasia", sa.String(length=255), nullable=False),
        sa.Column(
            "modo_publico_sus",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("cnes", sa.String(length=7), nullable=True),
        sa.Column(
            "tipo_unidade_sus",
            sa.String(length=64),
            server_default="UPA_DIGITAL_24H",
            nullable=False,
        ),
        sa.Column("ibge_municipio", sa.String(length=7), nullable=True),
        sa.Column(
            "ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_configuracoes_unidade"),
        sa.UniqueConstraint(
            "singleton_guard", name="uq_configuracoes_unidade_singleton"
        ),
        sa.CheckConstraint(
            "singleton_guard IS TRUE",
            name="chk_configuracoes_unidade_singleton",
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_profissionais"),
        sa.UniqueConstraint("email", name="uq_profissional_email"),
        sa.UniqueConstraint("cpf", name="uq_profissional_cpf"),
    )
    op.create_index("idx_profissionais_papel", "profissionais", ["papel"])

    # 5. Tabela de Pacientes
    op.create_table(
        "pacientes",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("cpf", sa.String(length=14), nullable=True),
        sa.Column("cns", sa.String(length=15), nullable=True),
        sa.Column("data_nascimento", sa.Date(), nullable=False),
        sa.Column("nome_completo", sa.String(length=255), nullable=True),
        sa.Column("nome_social", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_pacientes"),
        sa.CheckConstraint(
            "cpf IS NOT NULL OR cns IS NOT NULL",
            name="chk_documento_paciente_obrigatorio",
        ),
    )
    op.create_index(
        "uq_paciente_cpf",
        "pacientes",
        ["cpf"],
        unique=True,
        postgresql_where=sa.text("cpf IS NOT NULL"),
    )
    op.create_index(
        "uq_paciente_cns",
        "pacientes",
        ["cns"],
        unique=True,
        postgresql_where=sa.text("cns IS NOT NULL"),
    )
    op.create_index("idx_pacientes_telefone", "pacientes", ["telefone"])

    # 6. Tabela de Dependentes
    op.create_table(
        "dependentes",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
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

    # 7. Tabela de Passkeys WebAuthn do Paciente
    op.create_table(
        "paciente_passkeys",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.String(length=512), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column(
            "sign_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("device_name", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name="fk_paciente_passkeys_paciente_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paciente_passkeys"),
        sa.UniqueConstraint("credential_id", name="uq_paciente_passkeys_cred"),
    )
    op.create_index(
        "idx_paciente_passkeys_paciente", "paciente_passkeys", ["paciente_id"]
    )

    # 8. Tabela de Credenciais de Autenticação
    op.create_table(
        "usuarios_credenciais",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("identificador", sa.String(length=255), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("papel", sa.String(length=32), nullable=False),
        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "falhas_login_consecutivas",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("bloqueado_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret", sa.String(length=64), nullable=True),
        sa.Column(
            "mfa_ativo",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_usuarios_credenciais"),
        sa.UniqueConstraint(
            "identificador",
            name="uq_usuarios_credenciais_identificador",
        ),
    )
    op.create_index("idx_usuarios_credenciais_papel", "usuarios_credenciais", ["papel"])
    op.create_index(
        "idx_usuarios_credenciais_usuario_id",
        "usuarios_credenciais",
        ["usuario_id"],
    )

    # 9. Tabela de Atendimentos
    op.create_table(
        "atendimentos",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
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
            "prioridade_clinica BETWEEN 1 AND 5",
            name="chk_atendimento_prioridade",
        ),
    )
    op.create_index("idx_atendimentos_status", "atendimentos", ["status"])
    op.create_index("idx_atendimentos_paciente", "atendimentos", ["paciente_id"])
    op.create_index("idx_atendimentos_medico", "atendimentos", ["medico_id"])
    op.create_index(
        "idx_atendimentos_fila",
        "atendimentos",
        ["status", "prioridade_clinica", "data_entrada_fila"],
    )

    # 10. Tabela de Triagens
    op.create_table(
        "triagens",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("queixa_principal", sa.Text(), nullable=False),
        sa.Column(
            "sintomas_alerta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "escala_dor",
            sa.Integer(),
            server_default="0",
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
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_triagens_atendimento_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_triagens"),
        sa.UniqueConstraint("atendimento_id", name="uq_triagens_atendimento_id"),
        sa.CheckConstraint(
            "prioridade_calculada BETWEEN 1 AND 5",
            name="chk_triagem_prioridade",
        ),
        sa.CheckConstraint(
            "escala_dor BETWEEN 0 AND 10",
            name="chk_triagem_escala_dor",
        ),
    )

    # 11. Tabela de Evoluções Clínicas (SOAP)
    op.create_table(
        "evolucoes_clinicas",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("medico_id", sa.UUID(), nullable=False),
        sa.Column("anamnese", sa.Text(), nullable=False),
        sa.Column("exame_fisico_virtual", sa.Text(), nullable=True),
        sa.Column("cid10_principal", sa.String(length=10), nullable=True),
        sa.Column("conduta", sa.Text(), nullable=False),
        sa.Column(
            "codigo_sigtap",
            sa.String(length=16),
            server_default="03.01.01.025-0",
            nullable=False,
        ),
        sa.Column(
            "ia_utilizada",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("ia_modelo", sa.String(length=64), nullable=True),
        sa.Column("ia_sugestao_bruta", sa.Text(), nullable=True),
        sa.Column("ia_diff_modificacao", sa.Text(), nullable=True),
        sa.Column(
            "ia_ratificada_pelo_medico",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "identidade_verificada",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("tipo_documento_verificado", sa.String(length=16), nullable=True),
        sa.Column("justificativa_excecao_identidade", sa.Text(), nullable=True),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "atendimento_id", name="uq_evolucoes_clinicas_atendimento_id"
        ),
    )
    op.create_index(
        "idx_evolucoes_atendimento",
        "evolucoes_clinicas",
        ["atendimento_id"],
    )

    # 12. Tabela de Documentos Clínicos
    op.create_table(
        "documentos_clinicos",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("medico_id", sa.UUID(), nullable=False),
        sa.Column("tipo_documento", sa.String(length=32), nullable=False),
        sa.Column("chave_s3", sa.String(length=512), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=True),
        sa.Column("justificativa_tempo_inferior", sa.Text(), nullable=True),
        sa.Column("liveness_verificacao_hash", sa.String(length=128), nullable=True),
        sa.Column("justificativa_excecao_liveness", sa.Text(), nullable=True),
        sa.Column("assinado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
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
            "sha256_hash IS NULL OR length(sha256_hash) = 64",
            name="chk_documentos_sha256_len",
        ),
    )
    op.create_index(
        "idx_documentos_atendimento",
        "documentos_clinicos",
        ["atendimento_id"],
    )

    # 13. Tabela de Itens de Prescrição
    op.create_table(
        "documento_itens",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
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

    # 14. Tabela de Auditoria Imutável (Append-Only)
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("atendimento_id", sa.UUID(), nullable=True),
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
        ["ator_tipo", "ator_id"],
    )

    # Trigger anti-adulteração de auditoria (ADR-007)
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

    # 15. Tabela Singleton de Configuração do Plantão (Telemetria)
    op.create_table(
        "configuracoes_plantao",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "singleton_guard",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "medicos_ativos_planejados",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "alpha_backpressure",
            sa.Numeric(precision=4, scale=2),
            server_default="1.25",
            nullable=False,
        ),
        sa.Column(
            "cota_diaria_maxima",
            sa.Integer(),
            server_default="300",
            nullable=True,
        ),
        sa.Column(
            "tma_padrao_segundos",
            sa.Integer(),
            server_default="600",
            nullable=False,
        ),
        sa.Column(
            "tempo_tolerancia_ring_segundos",
            sa.Integer(),
            server_default="45",
            nullable=False,
        ),
        sa.Column(
            "modo_operacao",
            sa.String(length=32),
            server_default="SUS",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_1",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_2",
            sa.Integer(),
            server_default="10",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_3",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_4",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_5",
            sa.Integer(),
            server_default="240",
            nullable=False,
        ),
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
        sa.Column("atualizado_por_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_configuracoes_plantao"),
        sa.UniqueConstraint(
            "singleton_guard", name="uq_configuracoes_plantao_singleton"
        ),
        sa.CheckConstraint(
            "singleton_guard IS TRUE",
            name="chk_configuracoes_plantao_singleton",
        ),
        sa.CheckConstraint(
            "alpha_backpressure >= 1.20 AND alpha_backpressure <= 1.30",
            name="chk_config_plantao_alpha",
        ),
        sa.CheckConstraint(
            "tma_padrao_segundos >= 60",
            name="chk_config_plantao_tma",
        ),
        sa.CheckConstraint(
            "tempo_tolerancia_ring_segundos >= 10",
            name="chk_config_plantao_ring",
        ),
        sa.CheckConstraint(
            "modo_operacao IN ('SUS', 'PRIVADO')",
            name="chk_config_plantao_modo",
        ),
    )

    # 16. Tabela de Produção Ambulatorial (BPA-I / SISAB)
    op.create_table(
        "producoes_ambulatoriais",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("profissional_id", sa.UUID(), nullable=False),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("cnes", sa.String(length=7), nullable=False),
        sa.Column(
            "codigo_sigtap",
            sa.String(length=16),
            server_default="03.01.01.025-0",
            nullable=False,
        ),
        sa.Column(
            "carater_atendimento",
            sa.String(length=2),
            server_default="02",
            nullable=False,
        ),
        sa.Column("competencia", sa.String(length=6), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="CONSOLIDADO",
            nullable=False,
        ),
        sa.Column(
            "consolidado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_producoes_ambulatoriais_atendimento_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name="fk_producoes_ambulatoriais_paciente_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profissional_id"],
            ["profissionais.id"],
            name="fk_producoes_ambulatoriais_profissional_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_producoes_ambulatoriais"),
        sa.UniqueConstraint(
            "atendimento_id", name="uq_producoes_ambulatoriais_atendimento_id"
        ),
    )
    op.create_index(
        "idx_producao_atendimento", "producoes_ambulatoriais", ["atendimento_id"]
    )
    op.create_index(
        "idx_producao_competencia", "producoes_ambulatoriais", ["competencia"]
    )

    # 17. Tabelas de Agendamento Programado eMulti (Scheduling)
    op.create_table(
        "agenda_disponibilidades",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("profissional_id", sa.UUID(), nullable=False),
        sa.Column("especialidade", sa.String(length=40), nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        sa.Column("duracao_minutos", sa.Integer(), nullable=False),
        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dia_semana BETWEEN 0 AND 6",
            name="chk_agenda_disp_dia_semana",
        ),
        sa.CheckConstraint(
            "hora_fim > hora_inicio",
            name="chk_agenda_disp_horarios",
        ),
        sa.CheckConstraint(
            "duracao_minutos BETWEEN 15 AND 120",
            name="chk_agenda_disp_duracao",
        ),
        sa.ForeignKeyConstraint(
            ["profissional_id"],
            ["profissionais.id"],
            name="fk_agenda_disponibilidades_profissional_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agenda_disponibilidades"),
    )
    op.create_index(
        "idx_agenda_disp_esp",
        "agenda_disponibilidades",
        ["especialidade", "dia_semana"],
    )
    op.create_index(
        "idx_agenda_disp_prof",
        "agenda_disponibilidades",
        ["profissional_id"],
    )

    op.create_table(
        "agendamentos",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("profissional_id", sa.UUID(), nullable=False),
        sa.Column("especialidade", sa.String(length=40), nullable=False),
        sa.Column("slot_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_fim", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="AGENDADO",
            nullable=False,
        ),
        sa.Column("observacoes", sa.String(length=500), nullable=True),
        sa.Column("atendimento_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint(
            "slot_fim > slot_inicio",
            name="chk_agendamento_slot_valido",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'AGENDADO', 'CONFIRMADO', 'EM_ATENDIMENTO', "
            "'CONCLUIDO', 'CANCELADO', 'FALTA'"
            ")",
            name="chk_agendamento_status",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name="fk_agendamentos_paciente_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profissional_id"],
            ["profissionais.id"],
            name="fk_agendamentos_profissional_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            name="fk_agendamentos_atendimento_id",
            ondelete="RESTRICT",
        ),
        postgresql.ExcludeConstraint(
            ("profissional_id", "="),
            (
                sa.func.tstzrange(
                    sa.column("slot_inicio"),
                    sa.column("slot_fim"),
                    "[)",
                ),
                "&&",
            ),
            name="excl_agendamento_slot_ativo",
            using="gist",
            where=sa.text("status NOT IN ('CANCELADO', 'FALTA')"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agendamentos"),
    )
    op.create_index(
        "uq_agendamento_slot_ativo",
        "agendamentos",
        ["profissional_id", "slot_inicio"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('CANCELADO', 'FALTA')"),
    )
    op.create_index(
        "uq_agendamento_atendimento_id",
        "agendamentos",
        ["atendimento_id"],
        unique=True,
        postgresql_where=sa.text("atendimento_id IS NOT NULL"),
    )
    op.create_index(
        "idx_agendamentos_paciente",
        "agendamentos",
        ["paciente_id", "slot_inicio"],
    )
    op.create_index(
        "idx_agendamentos_profissional",
        "agendamentos",
        ["profissional_id", "slot_inicio"],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS trg_prevent_audit_mutation();")

    op.drop_table("agendamentos", if_exists=True)
    op.drop_table("agenda_disponibilidades", if_exists=True)
    op.drop_table("producoes_ambulatoriais", if_exists=True)
    op.drop_table("configuracoes_plantao", if_exists=True)
    op.drop_table("audit_events", if_exists=True)
    op.drop_table("documento_itens", if_exists=True)
    op.drop_table("documentos_clinicos", if_exists=True)
    op.drop_table("evolucoes_clinicas", if_exists=True)
    op.drop_table("triagens", if_exists=True)
    op.drop_table("atendimentos", if_exists=True)
    op.drop_table("usuarios_credenciais", if_exists=True)
    op.drop_table("paciente_passkeys", if_exists=True)
    op.drop_table("dependentes", if_exists=True)
    op.drop_table("pacientes", if_exists=True)
    op.drop_table("profissionais", if_exists=True)
    op.drop_table("configuracoes_unidade", if_exists=True)

    op.execute("DROP FUNCTION IF EXISTS gen_uuidv7();")
