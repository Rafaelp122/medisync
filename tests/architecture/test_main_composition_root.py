"""Architecture guard: main.py stays a lean composition root (Issue #68)."""

import ast
from pathlib import Path

from src.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "src" / "main.py"


def test_main_does_not_import_infrastructure() -> None:
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "infrastructure" in alias.name:
                    violations.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "infrastructure" in mod:
                violations.append(f"from {mod} import ...")
    assert not violations, "main.py must not import infrastructure:\n" + "\n".join(
        violations
    )


def test_openapi_routes_exact_baseline() -> None:
    expected_routes = {
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/patient/otp/request",
        "/api/v1/auth/patient/otp/verify",
        "/api/v1/auth/refresh",
        "/api/v1/consultations/{atendimento_id}/documents",
        "/api/v1/consultations/{atendimento_id}/documents/{documento_id}/pdf",
        "/api/v1/consultations/{atendimento_id}/documents/{documento_id}/sign",
        "/api/v1/consultations/{atendimento_id}/finalize",
        "/api/v1/consultations/{atendimento_id}/livekit/token",
        "/api/v1/consultations/{atendimento_id}/prescriptions/validate",
        "/api/v1/consultations/{atendimento_id}/prontuario",
        "/api/v1/consultations/{atendimento_id}/soap",
        "/api/v1/consultations/{atendimento_id}/tma-status",
        "/api/v1/documents/download/{token_validacao}",
        "/api/v1/documents/validate/{token_validacao}",
        "/api/v1/fila/admissao",
        "/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
        "/api/v1/fila/cancelar/{atendimento_id}",
        "/api/v1/fila/chamar-proximo",
        "/api/v1/fila/piora",
        "/api/v1/fila/posicao/{atendimento_id}",
        "/api/v1/onboarding/fase-1",
        "/api/v1/onboarding/fase-2",
        "/api/v1/pacientes/{id}/dependentes",
        "/api/v1/telemetria/config-plantao",
        "/api/v1/telemetria/painel",
        "/healthz",
    }
    openapi_routes = set(app.openapi()["paths"].keys())
    assert openapi_routes == expected_routes, (
        f"OpenAPI routes diff: {openapi_routes ^ expected_routes}"
    )
