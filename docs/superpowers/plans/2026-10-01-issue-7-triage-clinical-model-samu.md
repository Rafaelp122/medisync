# Issue #7: Modelo Clínico `Triagem`, Classificação de Risco e Salvaguarda SAMU 192 (RN04)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o modelo de domínio rico `Triagem` em `src/modules/triage/domain/models/triagem.py`, motor de classificação de risco clínico (ACR/SUS níveis 1 a 5), salvaguarda mandatória de deterioração e emergência (RN04 com acionamento do SAMU 192 via `EmergencyNotifierPort`), computação do hash criptográfico do TCLE (RN07) e persistência relacional 1:1 com `Atendimento` no PostgreSQL 17.

**Architecture:** Hexagonal Pragmático sem Mapper Hell (ADR-001). A entidade `Triagem` reside no domínio do módulo `triage` e o use case de acolhimento comunica-se com notificadores externos exclusivamente através da porta tipada `EmergencyNotifierPort` (PEP 544 `Protocol`). O módulo `triage` depende unicamente de `core` no `tach.toml`.

**Tech Stack:** Python 3.14+, SQLAlchemy 2.0 (assíncrono), PostgreSQL 17 (JSONB e constraints), `basedpyright` (strict mode), `tach`, `pytest`.

---

## Estrutura de Arquivos

```
src/modules/triage/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── exceptions.py             # EmergenciaCriticaSamuError, TriagemInvalidaError
│   ├── classification.py         # Motor de classificação clínica e hash TCLE
│   └── models/
│       ├── __init__.py
│       └── triagem.py            # Entidade rica Triagem com mapeamento SQLAlchemy 2.0
└── application/
    ├── __init__.py
    ├── ports/
    │   ├── __init__.py
    │   └── emergency_notifier.py # EmergencyAlertDTO e EmergencyNotifierPort
    └── services/
        ├── __init__.py
        └── triage_service.py     # SubmeterTriagemUseCase / AvaliarRiscoUseCase

tests/
├── factories/
│   └── triage.py                 # Factory tipada make_triagem
├── unit/
│   ├── test_triage_model.py      # Testes unitários do modelo, regras ACR e SAMU 192
│   └── test_factories.py         # Teste de sanidade da factory
└── integration/
    └── test_triage_persistence.py# Testes reais de persistência 1:1 no PostgreSQL 17
```

---

### Task 1: Exceções de Domínio, Motor de Classificação e Hash TCLE

**Files:**
- Create: `src/modules/triage/domain/exceptions.py`
- Create: `src/modules/triage/domain/classification.py`
- Create: `src/modules/triage/domain/__init__.py`
- Create: `tests/unit/test_triage_model.py`

- [ ] **Step 1: Escrever testes unitários que falham para o motor de classificação e hash TCLE**
- [ ] **Step 2: Executar teste para verificar falha**
- [ ] **Step 3: Implementar `exceptions.py` e `classification.py`**
- [ ] **Step 4: Executar teste para confirmar aprovação**

---

### Task 2: Entidade Rica `Triagem` (SQLAlchemy 2.0 e Invariantes)

**Files:**
- Create: `src/modules/triage/domain/models/triagem.py`
- Create: `src/modules/triage/domain/models/__init__.py`
- Modify: `src/modules/triage/domain/__init__.py`
- Modify: `tests/unit/test_triage_model.py`

- [ ] **Step 1: Escrever testes unitários para a entidade rica `Triagem`**
- [ ] **Step 2: Executar teste para verificar falha**
- [ ] **Step 3: Implementar a classe `Triagem` em `triagem.py`**
- [ ] **Step 4: Executar teste unitário para confirmar aprovação**

---

### Task 3: Porta `EmergencyNotifierPort` e Serviço de Triagem com Salvaguarda SAMU 192 (RN04)

**Files:**
- Create: `src/modules/triage/application/ports/emergency_notifier.py`
- Create: `src/modules/triage/application/ports/__init__.py`
- Create: `src/modules/triage/application/services/triage_service.py`
- Create: `src/modules/triage/application/services/__init__.py`
- Create: `src/modules/triage/application/__init__.py`
- Modify: `tests/unit/test_triage_model.py`

- [ ] **Step 1: Escrever testes unitários para a salvaguarda SAMU 192 no serviço de triagem**
- [ ] **Step 2: Executar teste para verificar falha**
- [ ] **Step 3: Implementar `EmergencyNotifierPort` e `TriageService`**
- [ ] **Step 4: Executar testes unitários para confirmar aprovação**

---

### Task 4: Factory Tipada para `Triagem`

**Files:**
- Create: `tests/factories/triage.py`
- Modify: `tests/unit/test_factories.py`

- [ ] **Step 1: Escrever teste de sanidade da factory em `test_factories.py`**
- [ ] **Step 2: Implementar `tests/factories/triage.py`**
- [ ] **Step 3: Executar testes de factories para confirmar aprovação**

---

### Task 5: Testes de Persistência Relacional 1:1 no PostgreSQL 17

**Files:**
- Create: `tests/integration/test_triage_persistence.py`

- [ ] **Step 1: Escrever testes de integração reais contra PostgreSQL 17**
- [ ] **Step 2: Executar testes de integração**

---

### Task 6: Portão de Qualidade Completo e Governança

- [ ] **Step 1: Executar `just check`**
