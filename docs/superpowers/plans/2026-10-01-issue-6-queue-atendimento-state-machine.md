# Issue #6: Modelo Rico `Atendimento` e Máquina de Estados Finita (RN03)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o modelo de domínio rico `Atendimento` no módulo `queue` (`src/modules/queue/domain/models/atendimento.py`) com SQLAlchemy 2.0 (`Mapped[...]`), chaves primárias UUIDv7, máquina de estados finita determinística (RN03), taxonomia de gravidade clínica de 1 a 5 (RN01), validação criptográfica do TCLE (RN07, LGPD Art. 11), factory tipada e persistência relacional com constraints no PostgreSQL 17.

**Architecture:** Hexagonal Pragmático sem Mapper Hell (ADR-001). A entidade `Atendimento` reside no domínio do módulo `queue` e encapsula métodos e invariantes do ciclo de vida clínico. O módulo `queue` depende exclusivamente de `core` (`tach check`), desacoplado de `identity` através de chaves primárias relacionais.

**Tech Stack:** Python 3.14+, SQLAlchemy 2.0 (assíncrono), PostgreSQL 17, `basedpyright` (strict mode), `tach`, `pytest`.

---

## Estrutura de Arquivos

```
src/modules/queue/
├── __init__.py
└── domain/
    ├── __init__.py
    ├── exceptions.py             # TransicaoEstadoInvalidaError
    └── models/
        ├── __init__.py
        └── atendimento.py        # Atendimento, StatusAtendimento, PrioridadeClinica

tests/
├── factories/
│   └── queue.py                  # Factory tipada make_atendimento
├── unit/
│   ├── test_atendimento_model.py # Testes de regras de negócio, TCLE e máquina de estados
│   └── test_factories.py         # Teste de sanidade da factory
└── integration/
    └── test_atendimento_persistence.py # Testes de integridade e constraints no PostgreSQL 17
```

---

### Task 1: Exceções de Domínio e Enums da Fila

**Files:**
- Create: `src/modules/queue/domain/exceptions.py`
- Create: `src/modules/queue/domain/models/atendimento.py` (declaração inicial dos Enums)
- Create: `src/modules/queue/domain/models/__init__.py`
- Create: `src/modules/queue/domain/__init__.py`
- Create: `tests/unit/test_atendimento_model.py`

- [ ] **Step 1: Escrever testes unitários que falham para `StatusAtendimento`, `PrioridadeClinica` e `TransicaoEstadoInvalidaError`**
- [ ] **Step 2: Executar teste para verificar falha**
- [ ] **Step 3: Implementar `exceptions.py` e enums em `atendimento.py`**
- [ ] **Step 4: Executar teste para confirmar aprovação**

---

### Task 2: Entidade Rica `Atendimento` e Máquina de Estados (RN03)

**Files:**
- Modify: `src/modules/queue/domain/models/atendimento.py`
- Modify: `src/modules/queue/domain/models/__init__.py`
- Modify: `tests/unit/test_atendimento_model.py`

- [ ] **Step 1: Escrever testes unitários para a entidade rica `Atendimento`**
- [ ] **Step 2: Executar testes para verificar falhas**
- [ ] **Step 3: Implementar a classe `Atendimento` em `atendimento.py`**
- [ ] **Step 4: Executar testes unitários para confirmar aprovação**

---

### Task 3: Factory Tipada para `Atendimento`

**Files:**
- Create: `tests/factories/queue.py`
- Modify: `tests/unit/test_factories.py`

- [ ] **Step 1: Escrever teste unitário para a factory em `tests/unit/test_factories.py`**
- [ ] **Step 2: Executar teste para verificar falha**
- [ ] **Step 3: Implementar `tests/factories/queue.py`**
- [ ] **Step 4: Executar testes de factories para confirmar aprovação**

---

### Task 4: Testes de Persistência e Constraints no PostgreSQL 17

**Files:**
- Create: `tests/integration/test_atendimento_persistence.py`

- [ ] **Step 1: Escrever testes de integração reais contra PostgreSQL 17**
- [ ] **Step 2: Executar testes de integração**

---

### Task 5: Portão de Qualidade Completo e Governança

- [ ] **Step 1: Executar `just check`**
