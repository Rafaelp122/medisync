# Issue #4: Pipeline de Middlewares e RFC 7807 Problem Details

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o pipeline de middlewares HTTP (Request ID UUIDv7, resolução de Tenant e Structured Logging) e tratamento de erros padronizado RFC 7807 Problem Details no módulo `src/core/`.

**Architecture:** Middlewares ASGI/FastAPI integrados a `ContextVar` para Request ID e Tenant ID, formatador de logs JSON estruturado, classes de exceção de domínio especializadas e handlers globais convertendo erros para `application/problem+json`.

**Tech Stack:** FastAPI, Pydantic v2, Python 3.12+ `contextvars`, `logging`, RFC 9562 (UUIDv7), `httpx` (testes).

---

## Estrutura de Arquivos

```
src/
├── core/
│   ├── config.py              # Existente
│   ├── context.py             # Modificar: adicionar current_request_id ContextVar
│   ├── database.py            # Existente
│   ├── uuid7.py               # Novo: gerador RFC 9562 UUIDv7 e validação
│   ├── errors.py              # Novo: modelo ProblemDetails RFC 7807 e exceções de domínio
│   ├── logging.py             # Novo: JSONFormatter estruturado para logs
│   └── middleware.py          # Novo: RequestID, TenantResolution e StructuredLogging
└── main.py                    # Novo: factory create_app() e instância app

tests/
├── unit/
│   ├── test_config.py         # Existente
│   ├── test_context.py        # Modificar: adicionar testes de request_id
│   ├── test_uuid7.py          # Novo: testes unitários do gerador UUIDv7
│   ├── test_errors.py         # Novo: testes unitários de ProblemDetails e DomainError
│   └── test_logging.py        # Novo: testes do JSONFormatter
└── integration/
    ├── test_database.py       # Existente
    ├── test_docker_topology.py# Existente
    └── test_pipeline.py       # Novo: testes de integração do pipeline de middlewares e erros
```

---

### Task 1: Dev Dependencies, ContextVar de Request ID e Utilitário UUIDv7

**Files:**
- Modify: `pyproject.toml`
- Create: `src/core/uuid7.py`
- Modify: `src/core/context.py`
- Create: `tests/unit/test_uuid7.py`
- Modify: `tests/unit/test_context.py`

- [ ] **Step 1: Adicionar `httpx` ao grupo dev do `pyproject.toml`**

Adicionar `"httpx>=0.27.0"` em `[dependency-groups] dev` no `pyproject.toml`:
```toml
[dependency-groups]
dev = [
    "basedpyright>=1.18.0",
    "httpx>=0.27.0",
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "pytest-xdist>=3.6.0",
    "ruff>=0.6.0",
    "tach>=0.18.0",
]
```

- [ ] **Step 2: Sincronizar ambiente com `uv sync`**

Run: `uv sync`
Expected: Instala `httpx` com sucesso.

- [ ] **Step 3: Escrever testes unitários que falham para `uuid7` e `current_request_id`**

Criar `tests/unit/test_uuid7.py`:
```python
import uuid
from src.core.uuid7 import is_valid_uuid, uuid7, uuid7_str


def test_uuid7_generation():
    u = uuid7()
    assert isinstance(u, uuid.UUID)
    assert u.version == 7
    assert u.variant == uuid.RFC_4122


def test_uuid7_str_format():
    s = uuid7_str()
    assert isinstance(s, str)
    assert len(s) == 36
    assert is_valid_uuid(s)


def test_is_valid_uuid():
    assert is_valid_uuid(str(uuid.uuid4()))
    assert is_valid_uuid(uuid7_str())
    assert not is_valid_uuid("not-a-uuid")
    assert not is_valid_uuid("")
```

Adicionar testes em `tests/unit/test_context.py`:
```python
from src.core.context import (
    current_request_id,
    get_current_request_id,
    request_id_context,
    reset_current_request_id,
    set_current_request_id,
)


def test_request_id_context_lifecycle():
    assert get_current_request_id() is None

    token = set_current_request_id("req-123")
    assert get_current_request_id() == "req-123"

    reset_current_request_id(token)
    assert get_current_request_id() is None


def test_request_id_context_manager():
    assert get_current_request_id() is None

    with request_id_context("req-abc"):
        assert get_current_request_id() == "req-abc"

    assert get_current_request_id() is None
```

- [ ] **Step 4: Executar testes para confirmar falha**

Run: `uv run pytest tests/unit/test_uuid7.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.core.uuid7'`.

- [ ] **Step 5: Implementar `src/core/uuid7.py` e atualizar `src/core/context.py`**

Criar `src/core/uuid7.py`:
```python
"""UUIDv7 generation conforming to RFC 9562."""

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Generate a UUIDv7 per RFC 9562.

    Uses native uuid.uuid7() if available (Python 3.14+), otherwise constructs
    the 128-bit structure using 48-bit millisecond timestamp and cryptographically
    secure random bytes.
    """
    if hasattr(uuid, "uuid7"):
        fn = getattr(uuid, "uuid7")
        return fn()  # type: ignore[no-any-return]

    timestamp_ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)

    b = bytearray(16)
    b[0:6] = timestamp_ms.to_bytes(6, byteorder="big")
    b[6] = 0x70 | (rand_bytes[0] & 0x0F)
    b[7] = rand_bytes[1]
    b[8] = 0x80 | (rand_bytes[2] & 0x3F)
    b[9:16] = rand_bytes[3:10]

    return uuid.UUID(bytes=bytes(b))


def uuid7_str() -> str:
    """Generate a UUIDv7 formatted as canonical hyphenated string."""
    return str(uuid7())


def is_valid_uuid(val: str) -> bool:
    """Validate whether a string is a valid UUID representation."""
    try:
        uuid.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False
```

Atualizar `src/core/context.py` para incluir `current_request_id`:
```python
# ContextVar tracking active request / correlation ID
current_request_id: ContextVar[str | None] = ContextVar(
    "current_request_id", default=None
)


def get_current_request_id() -> str | None:
    """Retrieve active request ID from current async context."""
    return current_request_id.get()


def set_current_request_id(request_id: str | None) -> Token[str | None]:
    """Explicitly set active request ID in current execution flow."""
    return current_request_id.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    """Restore previous request ID using token."""
    current_request_id.reset(token)


@contextmanager
def request_id_context(request_id: str | None) -> Generator[None, None, None]:
    """Context manager binding request ID for a code block."""
    token = set_current_request_id(request_id)
    try:
        yield
    finally:
        reset_current_request_id(token)
```

- [ ] **Step 6: Executar testes para confirmar que passam**

Run: `uv run pytest tests/unit/test_uuid7.py tests/unit/test_context.py -v`
Expected: PASS.

---

### Task 2: Modelo RFC 7807 Problem Details, Exceções de Domínio e Handlers

**Files:**
- Create: `src/core/errors.py`
- Create: `tests/unit/test_errors.py`

- [ ] **Step 1: Escrever teste unitário para `ProblemDetails` e `DomainError`**

Criar `tests/unit/test_errors.py`:
```python
from pydantic import ValidationError as PydanticValidationError
from src.core.errors import (
    BadRequestError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ProblemDetails,
    UnauthorizedError,
    ValidationError,
)


def test_problem_details_model():
    p = ProblemDetails(
        type="https://errors.medisync.com/not-found",
        title="Not Found",
        status=404,
        detail="Patient not found",
        instance="/api/v1/patients/123",
        request_id="req-123",
    )
    d = p.model_dump(exclude_none=True)
    assert d["status"] == 404
    assert d["title"] == "Not Found"
    assert d["detail"] == "Patient not found"
    assert d["request_id"] == "req-123"


def test_domain_error_hierarchy():
    err = NotFoundError("Patient not found")
    assert isinstance(err, DomainError)
    assert err.status_code == 404
    assert err.title == "Not Found"
    assert err.detail == "Patient not found"

    err_conflict = ConflictError("Resource already locked")
    assert err_conflict.status_code == 409
    assert err_conflict.title == "Conflict"

    err_unauth = UnauthorizedError("Missing token")
    assert err_unauth.status_code == 401

    err_forbidden = ForbiddenError("Access denied")
    assert err_forbidden.status_code == 403

    err_bad = BadRequestError("Invalid parameter")
    assert err_bad.status_code == 400

    err_val = ValidationError("Invalid payload")
    assert err_val.status_code == 422
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.core.errors'`.

- [ ] **Step 3: Implementar `src/core/errors.py`**

Criar `src/core/errors.py`:
```python
"""RFC 7807 Problem Details models, domain exceptions, and FastAPI exception handlers."""

import logging
from typing import Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.context import get_current_request_id

logger = logging.getLogger("medisync.errors")

RFC7807_MEDIA_TYPE = "application/problem+json"


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details representation."""

    type: str = Field(default="about:blank", description="URI reference identifying the problem type")
    title: str = Field(description="Short human-readable summary of the problem type")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Human-readable explanation specific to this occurrence")
    instance: str | None = Field(default=None, description="URI reference identifying specific occurrence")
    code: str | None = Field(default=None, description="Application-specific error code")
    request_id: str | None = Field(default=None, description="Correlation / Request ID")
    invalid_params: list[dict[str, Any]] | None = Field(
        default=None, description="Validation errors breakdown for 422 responses"
    )


class DomainError(Exception):
    """Base class for all business and domain exceptions."""

    status_code: int = 400
    title: str = "Bad Request"
    error_type: str = "about:blank"
    code: str = "DOMAIN_ERROR"

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        title: str | None = None,
        error_type: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if title is not None:
            self.title = title
        if error_type is not None:
            self.error_type = error_type
        if code is not None:
            self.code = code


class NotFoundError(DomainError):
    status_code = 404
    title = "Not Found"
    code = "NOT_FOUND"


class ConflictError(DomainError):
    status_code = 409
    title = "Conflict"
    code = "CONFLICT"


class UnauthorizedError(DomainError):
    status_code = 401
    title = "Unauthorized"
    code = "UNAUTHORIZED"


class ForbiddenError(DomainError):
    status_code = 403
    title = "Forbidden"
    code = "FORBIDDEN"


class BadRequestError(DomainError):
    status_code = 400
    title = "Bad Request"
    code = "BAD_REQUEST"


class ValidationError(DomainError):
    status_code = 422
    title = "Unprocessable Entity"
    code = "VALIDATION_ERROR"


def create_problem_response(
    status: int,
    title: str,
    detail: str,
    *,
    error_type: str = "about:blank",
    instance: str | None = None,
    code: str | None = None,
    invalid_params: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    req_id = get_current_request_id()
    problem = ProblemDetails(
        type=error_type,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        code=code,
        request_id=req_id,
        invalid_params=invalid_params,
    )
    resp_headers = headers.copy() if headers else {}
    if req_id:
        resp_headers["X-Request-ID"] = req_id

    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type=RFC7807_MEDIA_TYPE,
        headers=resp_headers,
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Converts DomainError into RFC 7807 problem details response."""
    return create_problem_response(
        status=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        error_type=exc.error_type,
        instance=request.url.path,
        code=exc.code,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Converts FastAPI RequestValidationError into RFC 7807 problem details."""
    invalid_params: list[dict[str, Any]] = []
    for err in exc.errors():
        loc_str = " -> ".join(str(item) for item in err.get("loc", []))
        invalid_params.append({
            "name": loc_str,
            "reason": err.get("msg", ""),
            "type": err.get("type", ""),
        })

    return create_problem_response(
        status=422,
        title="Unprocessable Entity",
        detail="The request body or parameters failed validation.",
        error_type="about:blank",
        instance=request.url.path,
        code="VALIDATION_ERROR",
        invalid_params=invalid_params,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Converts Starlette HTTPException into RFC 7807 problem details."""
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    headers = exc.headers if hasattr(exc, "headers") else None
    return create_problem_response(
        status=exc.status_code,
        title="HTTP Error",
        detail=detail,
        instance=request.url.path,
        headers=headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches unhandled exceptions, logs internal traceback, and returns safe generic 500 RFC 7807 response."""
    logger.exception("Unhandled server exception: %s", exc)
    return create_problem_response(
        status=500,
        title="Internal Server Error",
        detail="An internal server error occurred. Please contact support.",
        instance=request.url.path,
        code="INTERNAL_SERVER_ERROR",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all RFC 7807 error handlers on the FastAPI application."""
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
```

- [ ] **Step 4: Executar testes de erros**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: PASS.

---

### Task 3: Formatador de Logs JSON Estruturado

**Files:**
- Create: `src/core/logging.py`
- Create: `tests/unit/test_logging.py`

- [ ] **Step 1: Escrever teste para `JSONFormatter`**

Criar `tests/unit/test_logging.py`:
```python
import json
import logging
from src.core.context import request_id_context, tenant_context
from src.core.logging import JSONFormatter


def test_json_formatter_standard_fields():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Sample log message",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Sample log message"
    assert "timestamp" in data


def test_json_formatter_with_contextvars():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Contextual log message",
        args=(),
        exc_info=None,
    )

    with request_id_context("req-999"), tenant_context(42):
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "req-999"
        assert data["tenant_id"] == 42
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.core.logging'`.

- [ ] **Step 3: Implementar `src/core/logging.py`**

Criar `src/core/logging.py`:
```python
"""Structured JSON logging configuration and formatter."""

from datetime import datetime, timezone
import json
import logging
from typing import Any

from src.core.context import get_current_request_id, get_current_tenant_id


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include active contextvars if bound
        req_id = get_current_request_id()
        if req_id is not None:
            log_entry["request_id"] = req_id

        tenant_id = get_current_tenant_id()
        if tenant_id is not None:
            log_entry["tenant_id"] = tenant_id

        # Merge extra attributes if passed
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_entry.update(record.extra_fields)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSONFormatter."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
```

- [ ] **Step 4: Executar testes de logging**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: PASS.

---

### Task 4: Middlewares: Request ID, Resolução de Tenant e Structured Logging

**Files:**
- Create: `src/core/middleware.py`
- Create: `tests/unit/test_middleware.py`

- [ ] **Step 1: Escrever testes unitários para a lógica de extração de Tenant e Request ID**

Criar `tests/unit/test_middleware.py`:
```python
from src.core.middleware import extract_tenant_from_header, extract_tenant_from_host


def test_extract_tenant_from_header():
    assert extract_tenant_from_header("101") == 101
    assert extract_tenant_from_header("   42   ") == 42
    assert extract_tenant_from_header(None) is None
    assert extract_tenant_from_header("invalid") is None
    assert extract_tenant_from_header("-5") is None


def test_extract_tenant_from_host():
    assert extract_tenant_from_host("101.medisync.local") == 101
    assert extract_tenant_from_host("tenant-42.medisync.local") == 42
    assert extract_tenant_from_host("medisync.com.br") is None
    assert extract_tenant_from_host("localhost:8000") is None
    assert extract_tenant_from_host("api.medisync.com.br") is None
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `uv run pytest tests/unit/test_middleware.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.core.middleware'`.

- [ ] **Step 3: Implementar `src/core/middleware.py`**

Criar `src/core/middleware.py`:
```python
"""HTTP Middlewares: Request ID, Tenant Resolution and Structured Access Logging."""

from collections.abc import Callable
import logging
import re
import time
from typing import Any
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.context import (
    reset_current_request_id,
    reset_current_tenant_id,
    set_current_request_id,
    set_current_tenant_id,
)
from src.core.uuid7 import is_valid_uuid, uuid7_str

logger = logging.getLogger("medisync.access")

REQUEST_ID_HEADER = "X-Request-ID"
TENANT_ID_HEADER = "X-Tenant-ID"

_SUBDOMAIN_TENANT_REGEX = re.compile(r"^(?:tenant-)?(\d+)(?:\.|$)", re.IGNORECASE)


def extract_tenant_from_header(header_val: str | None) -> int | None:
    """Extract integer tenant ID from X-Tenant-ID header if present and positive."""
    if not header_val:
        return None
    val_clean = header_val.strip()
    if val_clean.isdigit():
        t = int(val_clean)
        return t if t > 0 else None
    return None


def extract_tenant_from_host(host_val: str | None) -> int | None:
    """Extract integer tenant ID from host subdomain (e.g. 101.domain.com or tenant-42.domain.com)."""
    if not host_val:
        return None
    # Strip port if present
    host_only = host_val.split(":")[0].strip()
    match = _SUBDOMAIN_TENANT_REGEX.match(host_only)
    if match:
        t = int(match.group(1))
        return t if t > 0 else None
    return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensures every request has a valid UUIDv7 X-Request-ID, bound to contextvars and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        if incoming_id and is_valid_uuid(incoming_id):
            req_id = incoming_id
        else:
            req_id = uuid7_str()

        token = set_current_request_id(req_id)
        request.state.request_id = req_id

        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = req_id
            return response
        finally:
            reset_current_request_id(token)


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """Resolves active tenant ID from X-Tenant-ID header or subdomain and binds to ContextVar."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Prefer explicit X-Tenant-ID header
        tenant_id = extract_tenant_from_header(request.headers.get(TENANT_ID_HEADER))

        # 2. Fallback to subdomain extraction
        if tenant_id is None:
            tenant_id = extract_tenant_from_host(request.headers.get("host"))

        token = set_current_tenant_id(tenant_id)
        request.state.tenant_id = tenant_id

        try:
            return await call_next(request)
        finally:
            reset_current_tenant_id(token)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emits structured JSON access log for each request including duration, status, and tenant."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            client_ip = request.client.host if request.client else "unknown"

            log_extra: dict[str, Any] = {
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            }

            rec = logger.makeRecord(
                name=logger.name,
                level=logging.INFO,
                fn="",
                lno=0,
                msg=f"{request.method} {request.url.path} {status_code} ({duration_ms}ms)",
                args=(),
                exc_info=None,
            )
            rec.extra_fields = log_extra  # type: ignore[attr-defined]
            logger.handle(rec)


def setup_middlewares(app: FastAPI) -> None:
    """Setup middlewares in correct execution order (outermost first).

    Execution order on incoming request:
    1. RequestIDMiddleware (generates / binds request_id)
    2. TenantResolutionMiddleware (binds tenant_id)
    3. StructuredLoggingMiddleware (tracks latency & logs)
    """
    # Note: In Starlette, add_middleware prepends, so we add in reverse order of entry
    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(TenantResolutionMiddleware)
    app.add_middleware(RequestIDMiddleware)
```

- [ ] **Step 4: Executar testes de middlewares**

Run: `uv run pytest tests/unit/test_middleware.py -v`
Expected: PASS.

---

### Task 5: Application Factory e Testes de Integração End-to-End

**Files:**
- Create: `src/main.py`
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Implementar `src/main.py`**

Criar `src/main.py`:
```python
"""MediSync Express — FastAPI Application Entrypoint."""

from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.context import get_current_request_id, get_current_tenant_id
from src.core.errors import register_exception_handlers
from src.core.logging import setup_logging
from src.core.middleware import setup_middlewares


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    tenant_id: int | None
    request_id: str | None


def create_app() -> FastAPI:
    """Application factory for MediSync Express API."""
    settings = get_settings()
    setup_logging(level="DEBUG" if settings.debug else "INFO")

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 1. Register exception handlers (RFC 7807)
    register_exception_handlers(app)

    # 2. Setup middlewares pipeline
    setup_middlewares(app)

    # 3. System health route
    @app.get("/healthz", response_model=HealthCheckResponse)
    async def healthcheck() -> HealthCheckResponse:
        return HealthCheckResponse(
            status="ok",
            version="0.1.0",
            tenant_id=get_current_tenant_id(),
            request_id=get_current_request_id(),
        )

    return app


app = create_app()
```

- [ ] **Step 2: Criar suíte completa de testes de integração `tests/integration/test_pipeline.py`**

Criar `tests/integration/test_pipeline.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from src.core.context import get_current_tenant_id
from src.core.errors import ConflictError, NotFoundError
from src.main import create_app


class SamplePayload(BaseModel):
    name: str = Field(min_length=3)
    age: int = Field(ge=0)


@pytest.fixture
def app_with_routes():
    test_app = create_app()

    @test_app.get("/test/domain-error")
    async def route_domain_error():
        raise NotFoundError("Patient not found with specified ID")

    @test_app.get("/test/conflict-error")
    async def route_conflict_error():
        raise ConflictError("Patient already queued")

    @test_app.post("/test/validation-error")
    async def route_validation_error(payload: SamplePayload):
        return {"received": payload.name}

    @test_app.get("/test/unhandled-error")
    async def route_unhandled_error():
        raise RuntimeError("Secret database password / catastrophic crash")

    @test_app.get("/test/tenant-check")
    async def route_tenant_check():
        return {"tenant_id": get_current_tenant_id()}

    return test_app


@pytest.mark.asyncio
async def test_healthcheck_returns_request_id(app_with_routes):
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.get("/healthz")
        assert res.status_code == 200
        assert "x-request-id" in res.headers
        data = res.json()
        assert data["status"] == "ok"
        assert data["request_id"] == res.headers["x-request-id"]


@pytest.mark.asyncio
async def test_propagates_incoming_request_id(app_with_routes):
    custom_id = "01923456-789a-7def-8123-456789abcdef"
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.get("/healthz", headers={"X-Request-ID": custom_id})
        assert res.status_code == 200
        assert res.headers["x-request-id"] == custom_id
        assert res.json()["request_id"] == custom_id


@pytest.mark.asyncio
async def test_tenant_resolution_via_header(app_with_routes):
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.get("/test/tenant-check", headers={"X-Tenant-ID": "505"})
        assert res.status_code == 200
        assert res.json()["tenant_id"] == 505


@pytest.mark.asyncio
async def test_tenant_resolution_via_subdomain(app_with_routes):
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.get("/test/tenant-check", headers={"Host": "tenant-88.medisync.local"})
        assert res.status_code == 200
        assert res.json()["tenant_id"] == 88


@pytest.mark.asyncio
async def test_domain_error_returns_rfc7807(app_with_routes):
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.get("/test/domain-error")
        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 404
        assert body["title"] == "Not Found"
        assert body["detail"] == "Patient not found with specified ID"
        assert body["code"] == "NOT_FOUND"
        assert body["request_id"] == res.headers["x-request-id"]


@pytest.mark.asyncio
async def test_validation_error_returns_rfc7807(app_with_routes):
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.post("/test/validation-error", json={"name": "a", "age": -5})
        assert res.status_code == 422
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 422
        assert body["title"] == "Unprocessable Entity"
        assert "invalid_params" in body
        assert len(body["invalid_params"]) >= 2


@pytest.mark.asyncio
async def test_unhandled_500_does_not_leak_secrets(app_with_routes):
    async with AsyncClient(transport=ASGITransport(app=app_with_routes), base_url="http://test") as client:
        res = await client.get("/test/unhandled-error")
        assert res.status_code == 500
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 500
        assert body["title"] == "Internal Server Error"
        # Must NOT leak secret database message
        assert "catastrophic" not in body["detail"]
        assert "password" not in body["detail"]
        assert body["request_id"] == res.headers["x-request-id"]
```

- [ ] **Step 3: Executar testes de integração**

Run: `uv run pytest tests/integration/test_pipeline.py -v`
Expected: PASS com 7 testes aprovados.

---

### Task 6: Portão de Qualidade Completo e Governança Tach

**Files:**
- Verify: Todas as alterações em `src/` e `tests/`

- [ ] **Step 1: Executar `just check`**

Run: `just check`
Expected:
- `ruff format .` passa sem alterações.
- `ruff check . --fix` passa com 0 erros.
- `basedpyright` passa com 0 erros, 0 avisos.
- `tach check` valida os módulos com sucesso.
- `pytest` passa com 100% de cobertura nos arquivos do `src/core/`.

- [ ] **Step 2: Commit e Fechamento da Issue #4**

Run:
```bash
git add pyproject.toml uv.lock src/ tests/ docs/superpowers/plans/
git commit -m "feat(core): implement middleware pipeline and RFC 7807 problem details handler (#4)"
gh issue close 4 --comment "..."
```
