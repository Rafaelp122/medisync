# Issue #2: Docker Compose Topology & Dependabot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the complete container topology for local development (PostgreSQL 17 with UUID extensions, Valkey 8.0 with AOF, LiveKit SFU, and MinIO S3 with default bucket `medisync-docs`), alongside `.env.example`, `justfile` management recipes, automated integration test suite, and Dependabot configuration with single-PR grouping.

**Architecture:** Aligned with Hexagonal Pragmático infrastructure layer (C4 Level 2, ADR-002, ADR-005). Isolated, containerized runtime supporting multi-tenant RLS, atomic Lua queue scheduling, WebRTC media SFU, and S3-compatible document storage.

**Tech Stack:** Docker Compose v2, PostgreSQL 17 Alpine, Valkey 8.0 Alpine, LiveKit SFU v1.13+, MinIO Chainguard (`cgr.dev/chainguard/minio`), GitHub Dependabot, `pytest`, `just`.

---

## File Structure Map

```text
medisync/
├── .github/
│   └── dependabot.yml                             # Dependabot config with single-PR groups
├── docker-compose.yml                             # Multi-container topology with healthchecks
├── .env.example                                   # Local development environment variable template
├── scripts/
│   └── postgres/
│       └── 01-init-extensions.sql                 # PostgreSQL extensions initializer (uuid-ossp, pgcrypto)
├── justfile                                       # Added recipes: up, down, logs, ps, clean-docker
└── tests/
    └── integration/
        └── test_docker_topology.py                # Automated pytest suite validating services, ports & bucket
```

---

## Tasks

### Task 1: Configure GitHub Dependabot with Single-PR Grouping

**Files:**
- Create: `.github/dependabot.yml`

- [x] **Step 1: Write `.github/dependabot.yml` configuring `pip`, `github-actions`, and `docker` ecosystems**
- [x] **Step 2: Verify yaml syntax**

---

### Task 2: Create PostgreSQL 17 Extensions Initialization Script

**Files:**
- Create: `scripts/postgres/01-init-extensions.sql`

- [x] **Step 1: Write `scripts/postgres/01-init-extensions.sql` enabling `uuid-ossp` and `pgcrypto`**
- [x] **Step 2: Verify mounting in `/docker-entrypoint-initdb.d/`**

---

### Task 3: Create Development Environment Template (`.env.example`)

**Files:**
- Create: `.env.example`

- [x] **Step 1: Write `.env.example` with standard ports and credentials**
- [x] **Step 2: Copy to local `.env`**

---

### Task 4: Define Docker Compose Multi-Container Topology (`docker-compose.yml`)

**Files:**
- Create: `docker-compose.yml`

- [x] **Step 1: Configure `postgres` service with `postgres:17-alpine` and healthcheck**
- [x] **Step 2: Configure `valkey` service with `valkey/valkey:8.0-alpine`, AOF and healthcheck**
- [x] **Step 3: Configure `livekit` service with `livekit/livekit-server:latest`, dev mode and healthcheck**
- [x] **Step 4: Configure `minio` and `minio-init` services with Chainguard images and automatic bucket creation**
- [x] **Step 5: Verify all services start and report healthy**

---

### Task 5: Add Docker Management Recipes to `justfile`

**Files:**
- Modify: `justfile`

- [x] **Step 1: Add `up`, `down`, `logs`, `ps`, and `clean-docker` recipes**
- [x] **Step 2: Verify `just up` and `just ps` execute cleanly**

---

### Task 6: Add Integration Tests for Container Topology

**Files:**
- Create: `tests/integration/test_docker_topology.py`

- [x] **Step 1: Implement TCP port checks (5432, 6379, 7880, 9000, 9001)**
- [x] **Step 2: Implement PostgreSQL extension verification (`uuid-ossp`, `pgcrypto`)**
- [x] **Step 3: Implement Valkey `PING`/`PONG` check**
- [x] **Step 4: Implement LiveKit HTTP check (`http://localhost:7880`)**
- [x] **Step 5: Implement MinIO S3 API & Console checks (`http://localhost:9000`, `http://localhost:9001`)**
- [x] **Step 6: Implement MinIO bucket existence verification (`medisync-docs`)**
- [x] **Step 7: Run pytest suite and ensure 100% pass**

---

### Task 7: Full Quality Gate Verification & GitHub Issue Close

**Files:**
- None (verification & audit phase)

- [ ] **Step 1: Execute `just check`**
- [ ] **Step 2: Commit all changes with conventional commits**
- [ ] **Step 3: Close GitHub Issue #2**
