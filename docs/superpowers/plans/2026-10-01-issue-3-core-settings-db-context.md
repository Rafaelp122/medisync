# Issue #3: Application Settings, Async Database Engine (Psycopg 3), Granian and ContextVars Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement core foundation modules in `src/core/` for typed settings, async PostgreSQL database engine using Psycopg 3 with connection pooling and sessionmaker, multi-tenant `ContextVar` propagation and RLS transaction listener, Granian ASGI server integration, and full technical documentation update.

**Architecture:** Aligned with Hexagonal Pragmático infrastructure layer (C4 Level 2, ADR-003). Centralized typed configuration, transaction-scoped Row-Level Security (RLS) via `set_config('app.current_tenant_id', ..., true)`, and high-performance Rust-based ASGI runtime (Granian).

**Tech Stack:** Python 3.12+, FastAPI, Granian, SQLAlchemy 2.0 Async, Psycopg 3 (`psycopg[binary]`), Pydantic Settings, `basedpyright`, `pytest`, `just`.

---

## File Structure Map

```text
medisync/
├── pyproject.toml                         # Added dependencies: granian, psycopg[binary], sqlalchemy[asyncio]
├── .env.example                           # Updated DATABASE_URL for postgresql+psycopg://
├── README.md                              # Updated stack table with Granian and Psycopg 3
├── docs/
│   ├── 03-architecture/
│   │   ├── overview.md                    # C4 Level 2 diagram updated with Granian + Psycopg 3
│   │   └── data-model.md                  # Section 5 updated with Psycopg 3
│   └── adrs/
│       ├── ADR-002-Alocacao-Atomica-Valkey-Lua.md # Worker references updated to Granian
│       └── ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md # Connection pool references updated to Psycopg 3
├── src/
│   └── core/
│       ├── config.py                      # Pydantic BaseSettings loading .env and resolving async db url
│       ├── context.py                     # ContextVar for multi-tenant propagation and tenant_context manager
│       └── database.py                    # AsyncEngine, async_sessionmaker and RLS after_begin listener
└── tests/
    ├── unit/
    │   ├── test_config.py                 # Unit tests for settings, defaults and validation
    │   └── test_context.py                # Unit tests for ContextVar isolation and concurrency
    └── integration/
        └── test_database.py               # Integration tests for connection pool and RLS set_config injection
```

---

## Tasks

### Task 1: Update Project Dependencies

**Files:**
- Modify: `pyproject.toml`

- [x] **Step 1: Add `granian>=1.6.0`, `psycopg[binary]>=3.2.0`, and `sqlalchemy[asyncio]>=2.0.35`**
- [x] **Step 2: Sync dependencies via `uv sync`**

---

### Task 2: Update Development Environment Templates

**Files:**
- Modify: `.env.example`
- Modify: `.env`

- [x] **Step 1: Update `DATABASE_URL` to `postgresql+psycopg://...`**

---

### Task 3: Update Technical and Architectural Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/03-architecture/overview.md`
- Modify: `docs/03-architecture/data-model.md`
- Modify: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Modify: `docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`

- [x] **Step 1: Update API server references from Uvicorn to Granian (Rust)**
- [x] **Step 2: Update PostgreSQL driver references from asyncpg to Psycopg 3**
- [x] **Step 3: Update database and Valkey versions to PostgreSQL 17 and Valkey 8.0**

---

### Task 4: Implement Centralized Application Settings (`src/core/config.py`)

**Files:**
- Create: `src/core/config.py`

- [x] **Step 1: Define `Settings(BaseSettings)` with strict typing for all services**
- [x] **Step 2: Implement `async_database_url` computed property normalizing to `postgresql+psycopg://`**
- [x] **Step 3: Implement `@lru_cache def get_settings() -> Settings:` singleton accessor**

---

### Task 5: Implement Multi-Tenant Context (`src/core/context.py`)

**Files:**
- Create: `src/core/context.py`

- [x] **Step 1: Define `current_tenant_id: ContextVar[int | None]`**
- [x] **Step 2: Define getter, setter, and reset functions with Token typing**
- [x] **Step 3: Implement `@contextmanager def tenant_context(...)` ensuring safe reset via `finally`**

---

### Task 6: Implement Async Database Engine and RLS Listener (`src/core/database.py`)

**Files:**
- Create: `src/core/database.py`

- [x] **Step 1: Instantiate `AsyncEngine` with connection pooling parameters**
- [x] **Step 2: Instantiate `async_sessionmaker[AsyncSession]`**
- [x] **Step 3: Implement `after_begin` listener executing `SELECT set_config('app.current_tenant_id', :tenant_id, true)`**
- [x] **Step 4: Implement `get_db_session` dependency generator for FastAPI**

---

### Task 7: Implement Unit Tests for Settings and Context

**Files:**
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_context.py`

- [x] **Step 1: Test configuration defaults, environment overrides and validation errors**
- [x] **Step 2: Test ContextVar setting, resetting, exception resilience, and 50-task concurrency isolation**

---

### Task 8: Implement Integration Tests for Database and RLS

**Files:**
- Create: `tests/integration/test_database.py`

- [x] **Step 1: Test database connectivity with `SELECT 1`**
- [x] **Step 2: Test session transaction with tenant injects `app.current_tenant_id`**
- [x] **Step 3: Test session transaction without tenant sets empty string**
- [x] **Step 4: Test concurrent transactions maintain isolated RLS across pooled connections**

---

### Task 9: Execute Full Quality Gate and Close Issue #3

- [ ] **Step 1: Execute `just check` (Ruff format, Ruff lint, Basedpyright, Tach, Pytest)**
- [ ] **Step 2: Commit all changes with conventional commit**
- [ ] **Step 3: Close GitHub Issue #3**
