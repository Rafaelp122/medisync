-- MediSync Express — Extensões Mandatórias do PostgreSQL 17
-- Referência: docs/explanation/architecture/data-model.md

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
