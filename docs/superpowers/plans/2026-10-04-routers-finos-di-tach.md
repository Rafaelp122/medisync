# Routers Finos, DI com Depends e Fronteiras Tach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deixar 8 routers com responsabilidade única HTTP (bind, Depends, status, resposta), services com regra+transação, Tach com 0 violações.

**Architecture:** Presentation só `core + application + composition`. Services recebem ports via `Depends` em `composition.py` por módulo. Transação: um `commit()` por caso uso no service. Tenant único via `ContextVar` + `TenantDep`. Prefixo único `/api/v1`.

**Tech Stack:** FastAPI `Annotated+Depends`, SQLAlchemy 2.0 async (`expire_on_commit=False`), Tach, basedpyright strict, pytest, Ruff TID251.

---

## Baseline verificado 2026-10-04

- `git status`: 31 modificados + 7 novos (refactor ADR-008 não commitado). Fase 0 exige commit/stash antes.
- `tach check`: 13 FAIL:
  - `auth_service.py:52,60,73` application->infrastructure (hasher, token, rate_limiter)
  - `pep_service.py:65,73,81` application->infrastructure (pdf, signer, storage)
  - `alocacao_service.py:28,29` application->infrastructure (lua_manager)
  - `consultation_router.py:22` presentation->domain (`ConsultaInvalidaError`)
  - `document_validation_router.py:15` presentation->domain (`DocumentoClinico`)
  - `livekit_router.py:13` presentation->infrastructure (`get_livekit_adapter`)
  - `onboarding_router.py:13`, `pacientes_router.py:14` presentation->domain (`TenantInvalidoError`)
- `src/core/database.py:35-40`: `expire_on_commit=False, autoflush=False`. `refresh()` desnecessário salvo coluna server-generated.
- `src/core/context.py`: `current_tenant_id: ContextVar[int|None]`. Middleware resolve header/subdomínio, RLS `SET LOCAL app.current_tenant_id`, `SET LOCAL ROLE medisync_app` só com tenant.
- Breaking: prefixo único, tenant obrigatório (fim fallback `return 1`), `organizacao_id/medico_id` saem bodies Fase 5, services sem defaults.

Decisões Open Questions: `/api/v1` único (WS + `/healthz` sem versão, remove alias `/atendimentos`), Fase 5 via issues `#41->#39->#42->#40` (plano só prepara router), wiring per-módulo `composition.py` (sem `src/composition` global), validação pública falha integridade sem fabricar `Médico Assistente/00000`, Fase 10 vira issues novas exceto rate-limit pública que entra Fase 6.

---

## Princípios execução

- Um PR por bloco, `just check` verde ao final. Sem big bang.
- TDD: teste falha primeiro. Mudança mecânica pura: snapshot OpenAPI como rede.
- Bug embutido ganha regressão própria (rota fantasma, fallback tenant, ownership antes PSC).
- Não alterar comentários/docstrings alheios.

---

### Task 0: Fase 0 Baseline (S)

**Files:**
- Modify: `tach.toml` (stage A)
- Create: `scratch/openapi_before.json`
- Create: `tests/unit/test_route_table.py` (esqueleto, só coleta)

- [ ] **Step 1: Commitar baseline ADR-008**
```bash
git add -A && git status --short
git commit -m "refactor(adr008): padronizacao DTOs schemas sem mapper hell"
git checkout -b refactor/routers-di
```
Expected: `git status --short` limpo exceto branch nova.

- [ ] **Step 2: Registrar baseline just check com tach antigo**
```bash
git stash push -- tach.toml -m "stageB-temp"
just check 2>&1 | tee scratch/check_baseline.log
git stash pop
```
Expected: anotar falhas pré-existentes lint/tipos/testes. Não confundir com regressão.

- [ ] **Step 3: Aplicar Tach stage A**
```toml
# tach.toml stage A — source_roots=["."], módulos src.* sem camadas
source_roots = ["."]
exact = false
forbid_circular_dependencies = true
[[modules]]
path = "src.core"
depends_on = []
[[modules]]
path = "src.modules.auth"
depends_on = ["src.core"]
[[modules]]
path = "src.modules.consultation"
depends_on = ["src.core"]
[[modules]]
path = "src.modules.identity"
depends_on = ["src.core"]
[[modules]]
path = "src.modules.queue"
depends_on = ["src.core"]
[[modules]]
path = "src.modules.billing"
depends_on = ["src.core"]
[[modules]]
path = "src.modules.triage"
depends_on = ["src.core"]
[[modules]]
path = "src.worker"
depends_on = ["src.core", "src.modules.queue", "src.modules.billing"]
```
Run: `uv run tach check`
Expected: PASS. Valida inter-módulos de verdade (atual é no-op quebrado).

- [ ] **Step 4: Snapshot OpenAPI**
```python
# scratch/gen_openapi.py
from src.main import app
import json
spec = app.openapi()
json.dump({"paths": spec["paths"]}, open("scratch/openapi_before.json","w"), indent=2, sort_keys=True)
```
Run: `uv run python scratch/gen_openapi.py && wc -l scratch/openapi_before.json`
Expected: arquivo criado, usado diff Fases 1-2.

- [ ] **Step 5: Commit**
```bash
git add tach.toml scratch/openapi_before.json
git commit -m "chore(routers): baseline tach stageA + snapshot openapi"
```

---

### Task 1: Fase 1 Higiene rotas sem comportamento (S/M)

**Files:**
- Modify: `src/main.py:115-144`
- Modify: `src/core/database.py:67-70` (add `DbSessionDep`)
- Modify: `src/modules/consultation/presentation/dependencies.py` (add aliases)
- Modify: 5 routers (`auth_router.py`, `consultation_router.py`, `livekit_router.py`, `onboarding_router.py`, `pacientes_router.py`, `document_validation_router.py`)
- Modify: `tests/integration/test_auth_endpoints.py`, `test_consultation_endpoints.py`, `test_livekit_lifecycle.py`
- Modify: `docs/03-architecture/security-and-authorization.md`
- Create: `tests/unit/test_route_table.py`

- [ ] **Step 1: Teste tabela rotas falha primeiro**
```python
# tests/unit/test_route_table.py
from src.main import app
def test_no_double_prefix_and_single_handler():
    paths = [r.path for r in app.routes if hasattr(r,"path")]
    assert not any("/api/v1/api/v1" in p for p in paths)
    seen: set[tuple[str,str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        for m in methods:
            key = (m, getattr(route, "path", ""))
            assert key not in seen, f"duplicada {key}"
            seen.add(key)
def test_api_prefix():
    for r in app.routes:
        p = getattr(r, "path", "")
        if p.startswith("/") and not p.startswith(("/healthz","/docs","/openapi","/ws")):
            assert p.startswith("/api/v1"), f"sem prefixo {p}"
```
Run: `uv run pytest tests/unit/test_route_table.py -v`
Expected: FAIL (duplo prefixo + rotas raiz existem).

- [ ] **Step 2: DbSessionDep único**
```python
# src/core/database.py append
from typing import Annotated
from fastapi import Depends
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
```
Remover 6x `SessionDep = Annotated[...]` locais + imports `AsyncSession, get_db_session` não usados.

- [ ] **Step 3: Aliases path**
```python
# src/modules/consultation/presentation/dependencies.py append
from fastapi import Path
AtendimentoIdPath = Annotated[UUID, Path(description="Identificador único do atendimento")]
DocumentoIdPath = Annotated[UUID, Path(description="Identificador único do documento clínico")]
```
Trocar 10 declarações 3-linhas por alias.

- [ ] **Step 4: main.py prefixo único**
```python
# src/main.py
from fastapi import APIRouter
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth_router)
api_v1.include_router(onboarding_router)
api_v1.include_router(pacientes_router)
api_v1.include_router(livekit_router)
api_v1.include_router(consultation_router)
api_v1.include_router(validation_router)
app.include_router(api_v1)
app.include_router(queue_ws_router)
app.include_router(doctor_ws_router)
```
Remover `app.include_router(auth_router)` raiz + `app.include_router(auth_router, prefix="/api/v1")` duplicados. WS + `/healthz` sem versão.

- [ ] **Step 5: Routers declaram prefix+tags, removem decoradores empilhados**
```python
# exemplo auth_router.py
auth_router = APIRouter(prefix="/auth", tags=["Authentication & Sessions (OWASP)"])
@auth_router.post("/login", response_model=TokenResponse, status_code=200)
async def login(...): ...
# deletar @auth_router.post("/api/v1/auth/login", include_in_schema=False) (~46 linhas total 5 routers)
# deletar alias "/atendimentos/{id}/prontuario" em consultation_router.py:112-117
```
Cada router: `auth /auth`, `consultation /consultations`, `livekit /consultations` (mantém path full, só prefixo v1 vem de cima — ou prefix `/consultations` e paths relativos), `documents /documents`, `onboarding /onboarding`, `pacientes /pacientes`.

- [ ] **Step 6: Atualizar testes + docs**
```bash
rg -l '"/auth|"/onboarding|"/pacientes|"/documents|"/consultations' tests/ | xargs sed -i 's#"/auth#"/api/v1/auth#g; s#"/onboarding#"/api/v1/onboarding#g'
```
Ajuste manual `test_auth_endpoints.py`, `test_consultation_endpoints.py`, `test_livekit_lifecycle.py`. Docs: `/atendimentos/{id}/prontuario` -> `/api/v1/consultations/{id}/prontuario`.

- [ ] **Step 7: Run + commit**
```bash
uv run pytest tests/unit/test_route_table.py -v
just check
```
Expected: PASS. Diff OpenAPI só troca prefixo.
```bash
git add -A && git commit -m "refactor(routes): prefixo unico api-v1 sem duplicadas"
```

---

### Task 2: Fase 2 Política única tenant (M)

**Files:**
- Create: `src/core/dependencies.py`
- Modify: `src/core/errors.py` (se precisar `TenantInvalidoError` core)
- Modify: `src/modules/identity/domain/exceptions.py:70-79` (herdar/alias)
- Modify: `onboarding_router.py:29-39`, `pacientes_router.py:29-39`, `consultation_router.py:42-49`, `auth_router.py:47-52`

- [ ] **Step 1: Teste unitário tenant falha**
```python
# tests/unit/test_tenant_dep.py
import pytest
from src.core.dependencies import get_required_tenant_id
from src.core.context import tenant_context
def test_sem_contexto_400():
    from src.core.errors import BadRequestError
    with pytest.raises(BadRequestError):
        get_required_tenant_id_sync_for_test()  # wrapper sync chama lógica
def test_com_contexto_ok():
    with tenant_context(42):
        assert get_required_tenant_id_sync_for_test() == 42
```
Simplificação: testar função sync interna. Integração:
```python
# tests/integration/test_tenant_required.py
async def test_soap_sem_tenant_400(client):
    r = await client.post("/api/v1/consultations/00000000-0000-7000-8000-000000000000/soap", json={})
    assert r.status_code == 400
```
Run: `uv run pytest tests/unit/test_tenant_dep.py -v`
Expected: FAIL (arquivo não existe).

- [ ] **Step 2: Implementar core dependencies**
```python
# src/core/dependencies.py
from typing import Annotated
from fastapi import Depends
from src.core.context import get_current_tenant_id
from src.core.errors import BadRequestError
class TenantInvalidoError(BadRequestError):
    title = "Organização Inválida"
    code = "TENANT_INVALIDO"
    def __init__(self, detail: str = "Header X-Tenant-ID obrigatório e positivo.") -> None:
        super().__init__(detail, title=self.title, code=self.code)
async def get_required_tenant_id() -> int:
    tid = get_current_tenant_id()
    if tid is None or tid <= 0:
        raise TenantInvalidoError()
    return tid
async def get_optional_tenant_id() -> int | None:
    tid = get_current_tenant_id()
    return tid if tid is not None and tid > 0 else None
TenantDep = Annotated[int, Depends(get_required_tenant_id)]
OptionalTenantDep = Annotated[int | None, Depends(get_optional_tenant_id)]
```
`identity/domain/exceptions.py:70`: `from src.core.dependencies import TenantInvalidoError` re-export (alias) para compat, ou herdar. Manter `status/code/type` idênticos.

- [ ] **Step 3: Trocar usos**
```python
# onboarding_router.py / pacientes_router.py: deletar _get_required_tenant_id + TenantDep local
from src.core.dependencies import TenantDep
# consultation_router.py: deletar _resolve_tenant_id (return 1)
# handler passa a receber tenant_id: TenantDep; body.organizacao_id se divergir -> 403:
if request.organizacao_id is not None and request.organizacao_id != tenant_id:
    raise ForbiddenError("organizacao_id do corpo diverge do tenant.")
org_id = tenant_id
# auth login: org_id = body.organizacao_id or optional_tenant; se None -> ValidationError (move p/ factory LoginCommand.from_body_and_tenant ou helper 3 linhas em auth/presentation)
```
Atualizar testes integração consultation p/ enviar `X-Tenant-ID`.

- [ ] **Step 4: Run + commit**
```bash
uv run pytest tests/unit/test_tenant_dep.py tests/integration/test_tenant_required.py -v
just check
git add -A && git commit -m "refactor(tenant): politica unica TenantDep sem fallback"
```

---

### Task 3: Fase 3 Providers service e composition (L)

**Files:**
- Create: `src/modules/queue/application/ports/lua_script_port.py`
- Modify: `auth_service.py:40-77`, `pep_service.py:55-85`, `alocacao_service.py:38-50`
- Create: `src/modules/auth/composition.py`, `src/modules/consultation/composition.py`, `src/modules/identity/composition.py`, `src/modules/queue/composition.py`
- Modify: `src/core/config.py` (add `STORAGE_BACKEND`)
- Modify: `tests/helpers.py` (add `make_*_service`)
- Modify: routers (troca `session: DbSessionDep` por `service: XDep`), `tests/integration/test_livekit_lifecycle.py` override import

- [ ] **Step 1: Porta Lua**
```python
# src/modules/queue/application/ports/lua_script_port.py
from typing import Protocol, runtime_checkable
@runtime_checkable
class LuaScriptPort(Protocol):
    async def alocar_chamada(self, *, medico_id: str, atendimento_id: str, ttl_segundos: int = 45) -> int: ...
    # mapear métodos reais usados em alocacao_service.py (grep evalsha/run)
```
`LuaScriptManager` satisfaz estruturalmente, sem herança.

- [ ] **Step 2: Construtores estritos (remover defaults + import lazy)**
```python
# auth_service.py
def __init__(self, session: AsyncSession, hasher: PasswordHasherPort, token_service: TokenServicePort, rate_limiter: AuthRateLimiterPort) -> None:
    self._session = session; self._hasher = hasher; self._token_service = token_service; self._rate_limiter = rate_limiter
    settings = get_settings()
    self._max_attempts = settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS
    self._window_seconds = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS
# pep_service.py
def __init__(self, session: AsyncSession, pdf_generator: PDFGeneratorPort, signer: ICPBrasilSignerPort, storage: StoragePort) -> None: ...
# alocacao_service.py
def __init__(self, valkey: Redis, db_session: AsyncSession, lua_manager: LuaScriptPort, arq_pool: ArqRedis | None = None, notification_adapter: NotificationPort | None = None) -> None: ...
```
Grep call sites: `rg "PEPService\(|AuthService\(|AlocacaoChamadaService\(" src tests`.

- [ ] **Step 3: Settings storage**
```python
# src/core/config.py add
STORAGE_BACKEND: Literal["fake","s3"] = "fake"
```
Default `fake` dev, prod `s3` por env. Provider escolhe `FakeStorageAdapter` vs `S3StorageAdapter` (cliente injetado).

- [ ] **Step 4: composition.py por módulo**
```python
# src/modules/consultation/composition.py
from typing import Annotated
from fastapi import Depends
from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.infrastructure.pdf_generator import ReportLabPDFGenerator
from src.modules.consultation.infrastructure.pyhanko_signer import PyHankoSigner
from src.modules.consultation.infrastructure.s3_storage import FakeStorageAdapter, S3StorageAdapter
def get_storage(): 
    s = get_settings()
    return S3StorageAdapter(...) if s.STORAGE_BACKEND == "s3" else FakeStorageAdapter()
def get_pep_service(session: DbSessionDep) -> PEPService:
    return PEPService(session=session, pdf_generator=ReportLabPDFGenerator(), signer=PyHankoSigner(), storage=get_storage())
PEPServiceDep = Annotated[PEPService, Depends(get_pep_service)]
# mover get_livekit_adapter da infra p/ cá
# auth/composition.py: get_auth_service/AuthServiceDep, identity: get_onboarding_service/get_dependente_service, queue: get_alocacao_service
```
Tach stage B: `composition` pode depender `application,domain,infrastructure,core`.

- [ ] **Step 5: Routers usam Dep**
```python
# antes
async def salvar_evolucao_soap(..., session: DbSessionDep):
    service = PEPService(session)
# depois
from src.modules.consultation.composition import PEPServiceDep
async def salvar_evolucao_soap(..., service: PEPServiceDep):
```
Handlers que só usavam session p/ instanciar perdem parâmetro. Atualizar `dependency_overrides[get_livekit_adapter]` import novo.

- [ ] **Step 6: Helpers teste**
```python
# tests/helpers.py append
from unittest.mock import AsyncMock
def make_pep_service(session, **overrides):
    from src.modules.consultation.application.services.pep_service import PEPService
    return PEPService(session=session, pdf_generator=overrides.get("pdf", AsyncMock()), signer=overrides.get("signer", AsyncMock()), storage=overrides.get("storage", AsyncMock()))
def make_auth_service(session, **overrides): ...
```
Migrar testes existentes.

- [ ] **Step 7: Run + commit**
```bash
uv run pytest tests/unit/test_providers.py -v  # fake->Fake, s3->S3
just check
git add -A && git commit -m "refactor(di): composition providers sem defaults infra"
```

---

### Task 4: Fase 4 Transação no service (M)

**Files:**
- Modify: `pep_service.py:110-313,535-576`
- Modify: `consultation_router.py:57-80,177-213,221-246,341-384`
- Modify: `docs/adrs/ADR-001*` adendo + `AGENTS.md`

- [ ] **Step 1: Testes persistência sem commit router**
```python
# tests/integration/test_pep_transaction.py
async def test_soap_persiste_sem_commit_router(session_factory):
    svc = make_pep_service(session_factory())
    await svc.salvar_evolucao_soap(cmd)
    async with session_factory() as s2:
        row = (await s2.execute(select(EvolucaoClinica).where(...))).scalar_one_or_none()
        assert row is not None
async def test_sign_ownership_antes_psc(fake_signer_espião):
    with pytest.raises(NotFoundError):
        await svc.assinar_documento_clinico(documento_id_outro_atend, atendimento_id, creds)
    assert not fake_signer_espião.assinar_pdf.called
```
4 casos: soap, emitir, finalizar, assinar. Run FAIL.

- [ ] **Step 2: Commit no service + ownership primeiro**
```python
# pep_service.py cada caso uso fim:
await self._session.commit()
# assinar_documento_clinico nova assinatura:
async def assinar_documento_clinico(self, documento_id: UUID, atendimento_id: UUID, credenciais: DoctorCertificateCredentials) -> tuple[DocumentoClinico, bytes]:
    doc = ...scalar_one_or_none()
    if doc is None or doc.atendimento_id != atendimento_id:
        raise ConsultaInvalidaError(f"Documento '{documento_id}' não pertence ao atendimento '{atendimento_id}'.")
    ... checks finalizado ...
    pdf_bytes = await self.compilar_documento_pdf(documento_id)
    signed = await self._signer.assinar_pdf(pdf_bytes, credenciais)
    ... persist s3/cache ...
    await self._session.flush()
    await self._session.commit()
    return doc, signed
```
Regra: um commit por método público caso uso. Helpers/policies nunca commitam. `expire_on_commit=False` então sem `refresh` salvo server-generated.

- [ ] **Step 3: Limpar router**
Deletar 4x `await session.commit()` + 3x `refresh()` + bloco `if doc.atendimento_id != atendimento_id:368-375`. Handler assinar passa `atendimento_id`.

- [ ] **Step 4: Docs + run**
Adendo ADR-001 + AGENTS.md: "service commita, um por caso uso".
```bash
just check
git add -A && git commit -m "refactor(tx): commit no service um por caso uso"
```

---

### Task 5: Fase 5 AuthN/AuthZ via issues (L, recorte router)

Ordem `#41->#39->#42->#40`. Aqui só pontos router/dependência.

**5.1 Tenant do token (#41):** `get_current_user` async + middleware propaga `org_id` Bearer quando sem `X-Tenant-ID`. Sync `def` roda threadpool e perde ContextVar — deve ser `async def` ou ficar no middleware. Regra: header se presente (validado vs token exceto ADMIN_GLOBAL), senão `org_id` token.

**5.2 `/auth/me`:** unificar `AuthService.validar_access_token` vs `core.authz.token.decode_access_token` (comparar claims). Reescrever:
```python
from src.core.authz.dependencies import CurrentUserDep
from src.modules.auth.composition import AuthServiceDep
@auth_router.get("/me", response_model=UsuarioPerfilResponse)
async def me(user: CurrentUserDep, service: AuthServiceDep) -> UsuarioPerfilResponse:
    cred = await service.obter_usuario_por_id(user.usuario_id, user.organizacao_id)
    if cred is None: raise NotFoundError("Registro de credencial do usuário não encontrado.")
    return UsuarioPerfilResponse.model_validate(cred)
```
Teste 401 sem/malformado, 200 válido.

**5.3 #39 mutações clínicas:** dividir `clinical_read_router` / `clinical_mutation_router` com `dependencies=[Depends(require_clinical_access)]`. Policy ganha `is_mutation` (leitura permite CONCLUIDO, mutação não). Handler usa `current_user.usuario_id` como `medico_id`. Remover `medico_id, organizacao_id` de `RegistrarSOAPRequest, EmitirDocumentoRequest, FinalizarConsultaRequest`. Tabela guards: POST soap/documents/finalize/sign = mutação, GET soap/prontuario/tma/pdf = leitura, POST validate = `require_role(MEDICO)`. Fixture `auth_headers(papel, org_id, usuario_id)` JWT real, migrar ~15 usos.

**5.4 #42 LiveKit+WS:** novo `LiveKitRoomService` application monta `room_name/identity`, chama porta, devolve DTO com `server_url` (add `server_url` à porta, elimina `getattr localhost:7880`). `LiveKitTokenRequest` remove `organizacao_id` (corrige UUID->int transitório), `participant_id` médico vem token, paciente via `verify_intake_token`. WS `get_ws_current_user(?token=)` antes `accept()`, fecha `4401/4403`. `/ws/doctor/{medico_id}` exige `==usuario_id`, `/ws/queue/{atendimento_id}` exige posse paciente.

**5.5 #40 posse paciente:** `IntakeTokenDep/PatientOwnershipDep` em `identity/composition`. Fase2 onboarding + dependentes: 401 sem token, 403 divergente. Nota: depende token acolhimento, #44 passwordless pode mudar contrato — confirmar ordem antes iniciar.

---

### Task 6: Fase 6 Validação pública sem SQL router (L)

**Files:**
- Create: `src/modules/consultation/application/services/document_validation_service.py`
- Create: `src/modules/consultation/application/ports/document_directory_port.py`
- Modify: infra provedor/neutro (SQL cru organizacoes/profissionais/pacientes), `composition.py`
- Modify: `document_validation_router.py` (2 handlers ~6 linhas)
- Create: `src/core/privacy.py` ou `consultation/domain/privacy.py` (mascaramento puro)

- [ ] **Step 1: Testes service com fakes**
```python
def test_mascarar_cpf_invalido(): assert mascarar_cpf("abc") == "***.***.***-**"
def test_mascarar_nome_preposicao(): assert mascarar_nome("Maria da Silva") == "M**** da S****"
async def test_medico_ausente_erro_integridade(fake_dir_sem_medico):
    with pytest.raises(IntegrityError): await svc.validar(token)
async def test_download_redirect_true_false(...): ...
```
Status assinado vs emitido, chave S3 derivada função única (hoje duplicada router + `is_documento_assinado`).

- [ ] **Step 2: Portas + service**
```python
# ports/document_directory_port.py
class DocumentDirectoryPort(Protocol):
    async def obter_dados_verificacao(self, doc: DocumentoClinico) -> DirData: ...
@dataclass(frozen=True)
class DocumentoValidacaoResult: documento_id: UUID; tipo_documento: str; status_documento: str; sha256_hash: str; ... paciente_nome_mascarado: str; ...
@dataclass(frozen=True)
class DownloadResult: documento_id: UUID; download_url: str; expires_in_seconds: int; chave_s3: str
class DocumentValidationService:
    def __init__(self, session: AsyncSession, directory: DocumentDirectoryPort, storage: StoragePort): ...
    async def validar(self, token: str) -> DocumentoValidacaoResult: ...
    async def gerar_url_download(self, token: str, expiracao: int) -> DownloadResult: ...
```
Mascaramento LGPD função pura testável. `_garantir_no_storage` vai service sem `suppress(Exception)` genérico, exceções tipadas `StoragePort` + log motivo. Médico/paciente ausente -> erro integridade + log, nunca inventar.

- [ ] **Step 3: Router fino + rate-limit**
```python
@validation_router.get("/documents/validate/{token_validacao}", response_model=ValidarDocumentoResponse)
async def validar_documento(token_validacao: str, service: DocValidationDep) -> ValidarDocumentoResponse:
    result = await service.validar(token_validacao)
    return ValidarDocumentoResponse.model_validate(result)
```
Igual download (redirect bool + expiracao 60-3600). Add rate-limit Valkey (mesmo pattern auth) — endpoints públicos UUID sem throttle = enumeração. Risco RLS: rota pública sem tenant enxerga zero linhas com `SET LOCAL ""`; definir role privilegiada bypass ou tenant sistema, documentar + teste integração com RLS ligado. Grep final: router sem `sqlalchemy, domain.models, text`.

---

### Task 7: Fase 7 WS + realtime utils (S)

**Files:**
- Modify: `src/core/realtime.py` (add `stream_channel`)
- Modify: `queue_ws_router.py`, `doctor_ws_router.py`
- Modify: tests WS

- [ ] **Step 1: Helper**
```python
# src/core/realtime.py
async def stream_channel(websocket: WebSocket, valkey: Redis, channel: str, event: str, **ids: str) -> None:
    from datetime import UTC, datetime
    await websocket.accept()
    payload = {"event": event, "timestamp": datetime.now(UTC).isoformat(), **ids}
    await forward_pubsub_to_websocket(valkey=valkey, channel=channel, websocket=websocket, initial_payload=payload)
```
- [ ] **Step 2: Routers ~8 linhas**
```python
@queue_ws_router.websocket("/ws/queue/{atendimento_id}")
async def ws_queue_patient(websocket: WebSocket, atendimento_id: UUID, valkey: ValkeyDep, user: WsUserDep) -> None:
    await stream_channel(websocket, valkey, channel_queue_patient(atendimento_id), "CONNECTED", atendimento_id=str(atendimento_id))
```
Troca `get_valkey_pool()+Redis()+try/finally` por `ValkeyDep(get_valkey_client)`. Auth 5.4 roda antes `accept()`. Overrides `get_valkey_client` nos testes. Teste mantém READY/CONNECTED + forward mensagem.

---

### Task 8: Fase 8 Erros e respostas (M)

**Files:**
- Modify: `src/core/errors.py`, `consultation/domain/exceptions.py` (herdar core com status/type)
- Modify: `consultation_router.py:98,302-327,351-384`, `document_validation_router.py:241-255`
- Modify: `presentation/schemas.py`, `application/dtos.py`

- [ ] **Step 1: Mapear domínio->HTTP**
```python
# consultation/domain/exceptions.py
from src.core.errors import NotFoundError, ValidationError
class ConsultaInvalidaError(NotFoundError): code="CONSULTA_INVALIDA"
class ConsultaFinalizadaError(ConflictError): code="CONSULTA_FINALIZADA"
class PrescricaoFisicaObrigatoriaError(ValidationError): code="PRESCRICAO_FISICA_OBRIGATORIA"  # 422
class EvolucaoNaoEncontradaError(NotFoundError): code="EVOLUCAO_NAO_ENCONTRADA"
```
Registrar handler global já existe `register_exception_handlers`. Remover `try/except->HTTPException` pdf/sign + `HTTPException` nenhuma evolução.

- [ ] **Step 2: Schemas resposta (ADR-008)**
```python
class ValidarPrescricaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    status: str; medicamento: str; mensagem: str
class FinalizarConsultaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    status: str; atendimento_id: UUID; is_finalizado: bool; mensagem: str
class DownloadUrlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    documento_id: UUID; download_url: str; expires_in_seconds: int; chave_s3: str
# ProntuarioResumoDTO ganha atendimento_id; ProntuarioResponse.model_validate(dto)
# AssinarDocumentoResponse.model_validate(DocumentoAssinadoResult)
```
`datetime.now(UTC)` default e `900s` TMA saem router p/ service param opcional. Contratos payload existentes continuam passando. Remove 4 violações presentation->domain.

---

### Task 9: Fase 9 Tach strict + guardas (M)

**Files:**
- Modify: `tach.toml` (stage B), `pyproject.toml` (Ruff TID251), `tests/architecture/test_routers_are_thin.py`, `ADR-001 adendo`, `overview.md`, `AGENTS.md`, `docs/adrs/README.md`

- [ ] **Step 1: tach stage B**
```toml
[[modules]]
path = "src.modules.consultation.domain"
depends_on = ["src.core"]
[[modules]]
path = "src.modules.consultation.application"
depends_on = ["src.core", "src.modules.consultation.domain"]
[[modules]]
path = "src.modules.consultation.infrastructure"
depends_on = ["src.core", "src.modules.consultation.application", "src.modules.consultation.domain"]
[[modules]]
path = "src.modules.consultation.composition"
depends_on = ["src.core", "src.modules.consultation.application", "src.modules.consultation.domain", "src.modules.consultation.infrastructure"]
[[modules]]
path = "src.modules.consultation.presentation"
depends_on = ["src.core", "src.modules.consultation.application", "src.modules.consultation.composition"]
# repetir auth/identity/queue/billing/triage; worker: core + queue/billing camadas
```
Run `tach check` -> 0 violações.

- [ ] **Step 2: Teste arquitetural AST**
```python
# tests/architecture/test_routers_are_thin.py
import ast, pathlib
FORBIDDEN = ("sqlalchemy", "infrastructure", "domain.models", ".commit(", ".refresh(", "text(", "select(", "HTTPException", "Service(")
def test_routers_thin():
    for p in pathlib.Path("src/modules").rglob("presentation/routers/*.py"):
        tree = ast.parse(p.read_text())
        src = p.read_text()
        assert "sqlalchemy" not in src and "infrastructure" not in src and "domain.models" not in src
        assert ".commit(" not in src and "HTTPException" not in src or "dependencies" in str(p)
```
Sem dependência nova.

- [ ] **Step 3: Ruff banned-api**
```toml
[tool.ruff.lint.flake8-tidy-imports]
ban-api = ["sqlalchemy.text.text"]
# per-file-ignores temporário p/ 2 arquivos Fase10 até saírem
```
Docs: ADR-001 adendo camadas/composition/transação, overview nova camada, AGENTS.md "router nunca importa sqlalchemy/infrastructure, service commita um por caso uso". `just check` 0 erros.

---

## Verificação global

Automatizada cada fase: `just check` (fmt, lint, typecheck, tach, test) retorno 0. Fases 1-2: diff `scratch/openapi_before.json`. Regressões 3 bugs: rota fantasma, fallback tenant, ownership antes PSC.

Aceite final: `tach check` camadas 0 violações; grep routers sem `sqlalchemy|commit|HTTPException|infrastructure|Service(`; teste arquitetural verde; sem `/api/v1/api/v1`; prefixo único.

Manual: `fastapi dev` percorrer login->me->emitir->assinar->validar->baixar PDF; WS com/sem token.

PRs: 1 (0+1 M baixo), 2 (2 M médio contrato), 3 (3+4 L médio call sites), 4-7 (5 issues L alto segurança), 8 (6 L médio), 9 (7+8 M baixo), 10 (9 M baixo). Fase 10 follow-ups viram issues: `AtendimentoQueryPort` p/ `ClinicalAccessPolicy._verificar_finalizado` + `PEPService` SQL `atendimentos`, `_DOCUMENTOS_ASSINADOS_CACHE` persistência (mesmo problema `_REVOKED_TOKENS_CACHE` #41), RLS role privilegiada doc, storage S3 real.
