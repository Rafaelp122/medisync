# Issue #5: Modelos Ricos de Identidade (Organizacao, Profissional, Paciente, Dependente) com UUIDv7

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar os modelos de domínio ricos do módulo `identity` com SQLAlchemy 2.0 (`Mapped[...]`), chaves primárias UUIDv7, hashing de senha Argon2id, invariantes clínicas do SUS/CFM (pediatria com CNS e sem CPF) e factories de teste.

**Architecture:** Modelos ricos no domínio (`src/modules/identity/domain/models.py`) estendendo `DeclarativeBase` compartilhado em `src/core/database.py`, métodos encapsulando regras de negócio e validações, constraints relacionais e parciais no PostgreSQL 17, e factories tipadas em `tests/factories/identity.py`.

**Tech Stack:** SQLAlchemy 2.0, PostgreSQL 17, `pwdlib[argon2]`, RFC 9562 (UUIDv7), `basedpyright` strict, `pytest-asyncio`.

---

## Estrutura de Arquivos

```
src/
├── core/
│   ├── database.py                   # Modificar: exportar DeclarativeBase (Base)
│   └── security.py                   # Novo: utilitários de hash Argon2id (pwdlib)
└── modules/
    └── identity/
        ├── __init__.py
        └── domain/
            ├── __init__.py
            └── models.py             # Novo: Organizacao, Profissional, Paciente, Dependente

tests/
├── factories/
│   ├── __init__.py
│   └── identity.py                   # Novo: factories tipadas para modelos de identidade
├── unit/
│   ├── test_security.py              # Novo: testes unitários de hash Argon2id
│   ├── test_identity_models.py       # Novo: testes unitários de regras e invariantes dos modelos ricos
│   └── test_factories.py             # Novo: testes das factories
└── integration/
    └── test_identity_persistence.py  # Novo: testes de persistência real e constraints no PostgreSQL 17
```

---

### Task 1: Dependência `pwdlib[argon2]`, `Base` em `src/core/database.py` e Utilitários de Hash

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/core/database.py`
- Create: `src/core/security.py`
- Create: `tests/unit/test_security.py`

- [x] **Step 1: Adicionar `pwdlib[argon2]` ao `pyproject.toml`**

Adicionar `"pwdlib[argon2]>=0.2.0"` em `dependencies` no `pyproject.toml`:
```toml
dependencies = [
    "fastapi>=0.115.0",
    "granian>=1.6.0",
    "psycopg[binary]>=3.2.0",
    "pwdlib[argon2]>=0.2.0",
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
    "sqlalchemy[asyncio]>=2.0.35",
]
```

- [x] **Step 2: Sincronizar dependências com `uv sync`**

Run: `uv sync`
Expected: Instala `pwdlib` e `argon2-cffi`.

- [x] **Step 3: Exportar `Base` (DeclarativeBase) em `src/core/database.py`**

Adicionar em `src/core/database.py`:
```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base declarativa compartilhada para todos os modelos ricos do SQLAlchemy 2.0."""
    pass
```

- [x] **Step 4: Escrever teste unitário que falha para `src/core/security.py`**

Criar `tests/unit/test_security.py`:
```python
from src.core.security import hash_password, verify_password


def test_hash_password_generates_argon2id():
    pwd = "SecretPassword123!"
    h = hash_password(pwd)
    assert isinstance(h, str)
    assert h.startswith("$argon2id$")
    assert verify_password(pwd, h)
    assert not verify_password("WrongPassword", h)


def test_verify_password_invalid_hash():
    assert not verify_password("password", "invalid-hash-string")
```

- [x] **Step 5: Executar teste para verificar falha**

Run: `uv run pytest tests/unit/test_security.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.core.security'`.

- [x] **Step 6: Implementar `src/core/security.py`**

Criar `src/core/security.py`:
```python
"""Security and cryptographic hashing utilities using Argon2id."""

from pwdlib import PasswordHash

# Initialize PasswordHash with recommended Argon2id configuration
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Generate an Argon2id cryptographic hash for the given plain text password."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify whether a plain text password matches an Argon2id hash."""
    try:
        return _password_hash.verify(password, hashed_password)
    except Exception:
        return False
```

- [x] **Step 7: Executar teste de segurança para confirmar aprovação**

Run: `uv run pytest tests/unit/test_security.py -v`
Expected: PASS.

---

### Task 2: Modelos Ricos `Organizacao` e `Profissional`

**Files:**
- Create: `src/modules/identity/domain/models.py`
- Create: `tests/unit/test_identity_models.py`

- [x] **Step 1: Escrever testes unitários que falham para `Organizacao` e `Profissional`**

Criar `tests/unit/test_identity_models.py`:
```python
import pytest
from src.core.errors import ValidationError
from src.modules.identity.domain.models import Organizacao, Profissional


def test_organizacao_model_attributes_and_defaults():
    org = Organizacao(
        cnpj="12.345.676/0001-90",
        razao_social="Hospital Municipal Santa Clara",
        nome_fantasia="HM Santa Clara",
        modo_publico_sus=True,
    )
    assert org.cnpj == "12345676000190"  # Sanitize to digits
    assert org.is_sus() is True
    assert org.ativo is True
    assert "tma_estimado_segundos" in org.config_plantao


def test_organizacao_invalid_cnpj_raises_validation_error():
    with pytest.raises(ValidationError, match="CNPJ inválido"):
        Organizacao(
            cnpj="123",  # Invalid length
            razao_social="Clínica Exemplo",
            nome_fantasia="Exemplo",
        )


def test_profissional_medico_requires_crm_and_uf():
    with pytest.raises(ValidationError, match="CRM e UF são obrigatórios"):
        Profissional(
            organizacao_id=1,
            cpf="123.456.789-00",
            nome_completo="Dr. Roberto Silva",
            email="roberto@medisync.com",
            senha_hash="dummy",
            papel="MEDICO",
            crm=None,
            crm_uf=None,
        )


def test_profissional_password_hashing():
    prof = Profissional(
        organizacao_id=1,
        cpf="12345678900",
        nome_completo="Dra. Paula Souza",
        email="paula@medisync.com",
        senha_hash="",
        papel="MEDICO",
        crm="123456",
        crm_uf="SP",
    )
    prof.set_password("SenhaForte@2026")
    assert prof.senha_hash.startswith("$argon2id$")
    assert prof.verify_password("SenhaForte@2026") is True
    assert prof.verify_password("SenhaErrada") is False
    assert prof.is_medico() is True
```

- [x] **Step 2: Executar teste para verificar falha**

Run: `uv run pytest tests/unit/test_identity_models.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.modules.identity.domain.models'`.

- [x] **Step 3: Implementar `Organizacao` e `Profissional` em `src/modules/identity/domain/models.py`**

Criar `src/modules/identity/domain/models.py`:
```python
"""Identity Bounded Context rich domain models (SQLAlchemy 2.0)."""

from datetime import datetime, timezone
import re
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.security import hash_password, verify_password
from src.core.uuid7 import uuid7

PapelProfissional = Literal[
    "ADMIN_GLOBAL", "GESTOR_UNIDADE", "MEDICO", "FATURAMENTO"
]


def _clean_digits(val: str) -> str:
    return re.sub(r"\D", "", val)


class Organizacao(Base):
    """Tenant model representing municipalities or private healthcare institutions."""

    __tablename__ = "organizacoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cnpj: Mapped[str] = mapped_column(String(18), unique=True, nullable=False)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(255), nullable=False)
    modo_publico_sus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config_plantao: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "alpha_margem": 1.25,
            "tma_estimado_segundos": 600,
            "cota_diaria_maxima": 300,
        },
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        nome_fantasia: str,
        modo_publico_sus: bool = False,
        config_plantao: dict[str, Any] | None = None,
        ativo: bool = True,
    ) -> None:
        clean_cnpj = _clean_digits(cnpj)
        if len(clean_cnpj) != 14:
            raise ValidationError("CNPJ inválido: deve conter exatamente 14 dígitos numéricos.")

        super().__init__(
            cnpj=clean_cnpj,
            razao_social=razao_social,
            nome_fantasia=nome_fantasia,
            modo_publico_sus=modo_publico_sus,
            config_plantao=config_plantao or {
                "alpha_margem": 1.25,
                "tma_estimado_segundos": 600,
                "cota_diaria_maxima": 300,
            },
            ativo=ativo,
        )

    def is_sus(self) -> bool:
        return self.modo_publico_sus

    def ativar(self) -> None:
        self.ativo = True

    def desativar(self) -> None:
        self.ativo = False


class Profissional(Base):
    """Clinical staff, unit managers, and administrative users."""

    __tablename__ = "profissionais"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "email", name="uq_profissional_org_email"),
        UniqueConstraint("organizacao_id", "cpf", name="uq_profissional_org_cpf"),
        Index("idx_profissionais_org_papel", "organizacao_id", "papel"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    cpf: Mapped[str] = mapped_column(String(14), nullable=False)
    nome_completo: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[str] = mapped_column(String(32), nullable=False)
    crm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crm_uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        cpf: str,
        nome_completo: str,
        email: str,
        senha_hash: str,
        papel: str,
        crm: str | None = None,
        crm_uf: str | None = None,
        ativo: bool = True,
        id: UUID | None = None,
    ) -> None:
        clean_cpf = _clean_digits(cpf)
        if len(clean_cpf) != 11:
            raise ValidationError("CPF do profissional inválido: deve conter 11 dígitos numéricos.")

        if papel == "MEDICO" and (not crm or not crm_uf):
            raise ValidationError(
                "CRM e UF são obrigatórios para profissionais com papel MEDICO (CFM 2.314/2022)."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            cpf=clean_cpf,
            nome_completo=nome_completo,
            email=email.strip().lower(),
            senha_hash=senha_hash,
            papel=papel,
            crm=crm.strip() if crm else None,
            crm_uf=crm_uf.strip().upper() if crm_uf else None,
            ativo=ativo,
        )

    def is_medico(self) -> bool:
        return self.papel == "MEDICO"

    def set_password(self, plain_password: str) -> None:
        """Hash and update password using Argon2id."""
        self.senha_hash = hash_password(plain_password)

    def verify_password(self, plain_password: str) -> bool:
        """Verify password against stored Argon2id hash."""
        return verify_password(plain_password, self.senha_hash)

    def ativar(self) -> None:
        self.ativo = True

    def desativar(self) -> None:
        self.ativo = False
```

- [x] **Step 4: Executar testes de `Organizacao` e `Profissional`**

Run: `uv run pytest tests/unit/test_identity_models.py -v`
Expected: PASS.

---

### Task 3: Modelos Ricos `Paciente` e `Dependente` (Salvaguardas Pediátricas e CNS/CPF)

**Files:**
- Modify: `src/modules/identity/domain/models.py`
- Modify: `tests/unit/test_identity_models.py`

- [x] **Step 1: Escrever testes unitários para `Paciente` e `Dependente`**

Adicionar em `tests/unit/test_identity_models.py`:
```python
from datetime import date
from uuid import uuid4
from src.modules.identity.domain.models import Dependente, Paciente


def test_paciente_pediatrico_without_cpf_succeeds_with_cns():
    paciente = Paciente(
        organizacao_id=1,
        cpf=None,
        cns="123456789012345",
        data_nascimento=date.today(),
        nome_completo="Bebê Teste",
        telefone="(11) 98888-7777",
    )
    assert paciente.cpf is None
    assert paciente.cns == "123456789012345"
    assert paciente.is_pediatrico() is True


def test_paciente_adult_with_cpf_succeeds():
    paciente = Paciente(
        organizacao_id=1,
        cpf="123.456.789-01",
        cns=None,
        data_nascimento=date(1990, 5, 20),
        nome_completo="Carlos Silva",
        telefone="11999998888",
    )
    assert paciente.cpf == "12345678901"
    assert paciente.is_pediatrico() is False


def test_paciente_without_cpf_and_without_cns_raises_validation_error():
    with pytest.raises(ValidationError, match="Obrigatório informar CPF ou CNS"):
        Paciente(
            organizacao_id=1,
            cpf=None,
            cns=None,
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )


def test_paciente_alergias_management():
    paciente = Paciente(
        organizacao_id=1,
        cpf="12345678901",
        data_nascimento=date(1995, 1, 1),
        telefone="11999998888",
    )
    assert paciente.alergias == []
    paciente.adicionar_alergia("Dipirona")
    paciente.adicionar_alergia("Penicilina")
    assert paciente.tem_alergia("dipirona") is True
    assert paciente.tem_alergia("Amoxicilina") is False
    paciente.remover_alergia("dipirona")
    assert paciente.tem_alergia("Dipirona") is False


def test_dependente_self_reference_raises_validation_error():
    same_id = uuid4()
    with pytest.raises(ValidationError, match="Paciente não pode ser dependente de si mesmo"):
        Dependente(
            organizacao_id=1,
            titular_id=same_id,
            dependente_id=same_id,
            grau_parentesco="FILHO",
        )
```

- [x] **Step 2: Executar testes para confirmar falha antes da implementação**

Run: `uv run pytest tests/unit/test_identity_models.py -k "paciente or dependente" -v`
Expected: FAIL com `ImportError: cannot import name 'Paciente'`.

- [x] **Step 3: Implementar `Paciente` e `Dependente` em `src/modules/identity/domain/models.py`**

Adicionar classes `Paciente` e `Dependente`:
```python
class Paciente(Base):
    """Patient model supporting adult and pediatric two-phase onboarding."""

    __tablename__ = "pacientes"
    __table_args__ = (
        CheckConstraint(
            "cpf IS NOT NULL OR cns IS NOT NULL",
            name="chk_documento_paciente_obrigatorio",
        ),
        Index("uq_paciente_org_cpf", "organizacao_id", "cpf", unique=True, postgresql_where=text("cpf IS NOT NULL")),
        Index("uq_paciente_org_cns", "organizacao_id", "cns", unique=True, postgresql_where=text("cns IS NOT NULL")),
        Index("idx_pacientes_org_telefone", "organizacao_id", "telefone"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    cns: Mapped[str | None] = mapped_column(String(15), nullable=True)
    data_nascimento: Mapped[date] = mapped_column(Date, nullable=False)
    nome_completo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_mae: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sexo_biologico: Mapped[str | None] = mapped_column(String(1), nullable=True)
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(2), nullable=True)
    alergias: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        data_nascimento: date,
        telefone: str,
        cpf: str | None = None,
        cns: str | None = None,
        nome_completo: str | None = None,
        nome_mae: str | None = None,
        sexo_biologico: str | None = None,
        cep: str | None = None,
        logradouro: str | None = None,
        numero: str | None = None,
        bairro: str | None = None,
        cidade: str | None = None,
        estado: str | None = None,
        alergias: list[str] | None = None,
        id: UUID | None = None,
    ) -> None:
        clean_cpf = _clean_digits(cpf) if cpf else None
        clean_cns = _clean_digits(cns) if cns else None

        if not clean_cpf and not clean_cns:
            raise ValidationError(
                "Obrigatório informar CPF ou CNS para o cadastro do paciente (CFM/SUS)."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            cpf=clean_cpf,
            cns=clean_cns,
            data_nascimento=data_nascimento,
            telefone=_clean_digits(telefone),
            nome_completo=nome_completo,
            nome_mae=nome_mae,
            sexo_biologico=sexo_biologico.upper() if sexo_biologico else None,
            cep=_clean_digits(cep) if cep else None,
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            cidade=cidade,
            estado=estado.upper() if estado else None,
            alergias=alergias or [],
        )

    def is_pediatrico(self) -> bool:
        today = date.today()
        idade = (
            today.year
            - self.data_nascimento.year
            - ((today.month, today.day) < (self.data_nascimento.month, self.data_nascimento.day))
        )
        return idade < 18

    def adicionar_alergia(self, medicamento: str) -> None:
        med_clean = medicamento.strip()
        if not self.tem_alergia(med_clean):
            # Create a new list copy to trigger SQLAlchemy dirty tracking
            self.alergias = [*self.alergias, med_clean]

    def remover_alergia(self, medicamento: str) -> None:
        target = medicamento.strip().lower()
        self.alergias = [a for a in self.alergias if a.strip().lower() != target]

    def tem_alergia(self, medicamento: str) -> bool:
        target = medicamento.strip().lower()
        return any(a.strip().lower() == target for a in self.alergias)


class Dependente(Base):
    """Pediatric or legal dependent linkage to titular patient."""

    __tablename__ = "dependentes"
    __table_args__ = (
        UniqueConstraint("titular_id", "dependente_id", name="uq_dependente_vinculo"),
        Index("idx_dependentes_org", "organizacao_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    titular_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pacientes.id", ondelete="RESTRICT"), nullable=False
    )
    dependente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pacientes.id", ondelete="RESTRICT"), nullable=False
    )
    grau_parentesco: Mapped[str] = mapped_column(String(32), nullable=False)
    vinculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        titular_id: UUID,
        dependente_id: UUID,
        grau_parentesco: str,
        id: UUID | None = None,
    ) -> None:
        if titular_id == dependente_id:
            raise ValidationError("Paciente não pode ser dependente de si mesmo.")

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            titular_id=titular_id,
            dependente_id=dependente_id,
            grau_parentesco=grau_parentesco.strip().upper(),
        )
```

- [x] **Step 4: Executar testes de modelos para confirmar aprovação**

Run: `uv run pytest tests/unit/test_identity_models.py -v`
Expected: PASS com 8 testes aprovados.

---

### Task 4: Model Factories para Testes

**Files:**
- Create: `tests/factories/__init__.py`
- Create: `tests/factories/identity.py`
- Create: `tests/unit/test_factories.py`

- [x] **Step 1: Criar geradores de factories tipadas em `tests/factories/identity.py`**

Criar `tests/factories/identity.py`:
```python
"""Typed model factories for identity entities used across tests."""

from datetime import date
from typing import Any
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.identity.domain.models import Dependente, Organizacao, Profissional, Paciente


def make_organizacao(
    *,
    cnpj: str = "12345678000195",
    razao_social: str = "Unidade Básica de Saúde Central",
    nome_fantasia: str = "UBS Central",
    modo_publico_sus: bool = True,
    config_plantao: dict[str, Any] | None = None,
    ativo: bool = True,
) -> Organizacao:
    return Organizacao(
        cnpj=cnpj,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        modo_publico_sus=modo_publico_sus,
        config_plantao=config_plantao,
        ativo=ativo,
    )


def make_profissional(
    organizacao_id: int = 1,
    *,
    cpf: str = "11122233344",
    nome_completo: str = "Dr. Carlos Plantonista",
    email: str = "carlos@medisync.local",
    senha_hash: str = "hash-default",
    papel: str = "MEDICO",
    crm: str | None = "998877",
    crm_uf: str | None = "SP",
    id: UUID | None = None,
) -> Profissional:
    return Profissional(
        organizacao_id=organizacao_id,
        cpf=cpf,
        nome_completo=nome_completo,
        email=email,
        senha_hash=senha_hash,
        papel=papel,
        crm=crm,
        crm_uf=crm_uf,
        id=id or uuid7(),
    )


def make_paciente(
    organizacao_id: int = 1,
    *,
    cpf: str | None = "55566677788",
    cns: str | None = None,
    data_nascimento: date | None = None,
    nome_completo: str = "Maria dos Santos",
    telefone: str = "11987654321",
    alergias: list[str] | None = None,
    id: UUID | None = None,
) -> Paciente:
    return Paciente(
        organizacao_id=organizacao_id,
        cpf=cpf,
        cns=cns,
        data_nascimento=data_nascimento or date(1985, 3, 15),
        nome_completo=nome_completo,
        telefone=telefone,
        alergias=alergias,
        id=id or uuid7(),
    )


def make_dependente(
    organizacao_id: int = 1,
    titular_id: UUID | None = None,
    dependente_id: UUID | None = None,
    *,
    grau_parentesco: str = "FILHO",
) -> Dependente:
    return Dependente(
        organizacao_id=organizacao_id,
        titular_id=titular_id or uuid7(),
        dependente_id=dependente_id or uuid7(),
        grau_parentesco=grau_parentesco,
    )
```

- [x] **Step 2: Escrever testes unitários para as factories em `tests/unit/test_factories.py`**

Criar `tests/unit/test_factories.py`:
```python
from tests.factories.identity import (
    make_dependente,
    make_organizacao,
    make_paciente,
    make_profissional,
)


def test_factories_creation():
    org = make_organizacao()
    assert org.cnpj == "12345678000195"

    prof = make_profissional(org.id or 1)
    assert prof.is_medico() is True

    paciente = make_paciente(org.id or 1)
    assert paciente.cpf == "55566677788"

    dep = make_dependente(org.id or 1)
    assert dep.grau_parentesco == "FILHO"
```

- [x] **Step 3: Executar testes das factories**

Run: `uv run pytest tests/unit/test_factories.py -v`
Expected: PASS.

---

### Task 5: Testes de Persistência Real no PostgreSQL 17

**Files:**
- Create: `tests/integration/test_identity_persistence.py`

- [x] **Step 1: Implementar suíte de testes de persistência real com AsyncSession**

Criar `tests/integration/test_identity_persistence.py`:
```python
from datetime import date
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.core.database import Base, async_session_factory, engine
from src.modules.identity.domain.models import Dependente, Organizacao, Paciente, Profissional
from tests.factories.identity import (
    make_dependente,
    make_organizacao,
    make_paciente,
    make_profissional,
)


@pytest.fixture(scope="module", autouse=True)
async def setup_identity_tables():
    """Create tables in PostgreSQL before testing and drop on cleanup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_persist_organizacao_and_profissional():
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="98765432000199", razao_social="Prefeitura Municipal")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        assert org.id is not None
        assert org.id > 0

        prof = make_profissional(organizacao_id=org.id, email="plantao@prefeitura.gov.br", cpf="12345678909")
        prof.set_password("Argon2SecurePassword")
        session.add(prof)
        await session.commit()
        await session.refresh(prof)

        assert prof.id is not None
        assert prof.verify_password("Argon2SecurePassword") is True


@pytest.mark.asyncio
async def test_profissional_unique_email_per_org_violation():
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="11223344000155")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        p1 = make_profissional(org.id, email="duplicado@org.com", cpf="11111111111")
        session.add(p1)
        await session.commit()

        p2 = make_profissional(org.id, email="duplicado@org.com", cpf="22222222222")
        session.add(p2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_paciente_pediatrico_persisted_without_cpf():
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="33445566000177")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        recem_nascido = make_paciente(
            org.id,
            cpf=None,
            cns="898000123456789",
            data_nascimento=date.today(),
            nome_completo="Recém Nascido de Maria",
        )
        session.add(recem_nascido)
        await session.commit()
        await session.refresh(recem_nascido)

        assert recem_nascido.id is not None
        assert recem_nascido.cpf is None
        assert recem_nascido.cns == "898000123456789"


@pytest.mark.asyncio
async def test_dependente_linkage_persisted():
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55667788000188")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        titular = make_paciente(org.id, cpf="77788899900", nome_completo="Mãe Titular")
        filho = make_paciente(org.id, cpf=None, cns="777000111222333", nome_completo="Filho Dependente")
        session.add_all([titular, filho])
        await session.commit()
        await session.refresh(titular)
        await session.refresh(filho)

        dep = make_dependente(org.id, titular_id=titular.id, dependente_id=filho.id, grau_parentesco="FILHO")
        session.add(dep)
        await session.commit()
        await session.refresh(dep)

        assert dep.id is not None
        assert dep.titular_id == titular.id
        assert dep.dependente_id == filho.id
```

- [x] **Step 2: Executar testes de integração contra o PostgreSQL 17**

Run: `uv run pytest tests/integration/test_identity_persistence.py -v`
Expected: PASS com 4 testes aprovados.

---

### Task 6: Portão de Qualidade Completo, Governança Tach e Fechamento

**Files:**
- Verify: Todas as alterações em `src/` e `tests/`

- [x] **Step 1: Executar `just check`**

Run: `just check`
Expected:
- `ruff format .` passa sem alterações.
- `ruff check . --fix` passa com 0 erros.
- `basedpyright` passa com 0 erros, 0 avisos.
- `tach check` valida fronteiras modulares com 0 violações.
- `pytest` passa com alta cobertura de testes.

- [x] **Step 2: Commit e Fechamento da Issue #5 no GitHub**

Run:
```bash
git add pyproject.toml uv.lock src/ tests/ docs/superpowers/plans/
git commit -m "feat(identity): implement Organizacao, Profissional, Paciente and Dependente models with UUIDv7 (#5)"
gh issue close 5 --comment "..."
```
