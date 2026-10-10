-- MediSync Express — Extensões Mandatórias do PostgreSQL 17
-- Referência: docs/03-architecture/data-model.md

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medisync_app') THEN
        CREATE ROLE medisync_app NOBYPASSRLS;
    END IF;
END
$$;
