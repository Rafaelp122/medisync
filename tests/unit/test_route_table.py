"""Tabela de rotas — baseline Fase 0 (routers-di, ADR-001/ADR-008).

Documenta o problema atual: duplo prefixo /api/v1/api/v1 e handlers
duplicados por include duplo em src/main.py. Estes testes FALHAM no
baseline e devem PASSAR após a Fase 1 (routers finos, include único).
Não corrigir rotas nesta task.
"""

from collections import Counter
from collections.abc import Iterable
from typing import Any, cast

from src.main import app

_NON_API_PATHS = frozenset(
    {"/healthz", "/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}
)


def _expand(routes: Iterable[Any]) -> Iterable[Any]:
    """Expande _IncludedRouter lazy (FastAPI>=0.14x) até as rotas efetivas."""
    for route in routes:
        expand: Any = getattr(route, "effective_candidates", None)
        if callable(expand):
            nested: Iterable[Any] = cast("Iterable[Any]", expand())
            yield from _expand(nested)
        else:
            yield getattr(route, "original_route", route)


def _http_routes() -> list[tuple[frozenset[str], str]]:
    """Lista (methods, path) de rotas HTTP; ignora websockets."""
    entries: list[tuple[frozenset[str], str]] = []
    for route in _expand(app.routes):
        raw_methods: Any = getattr(route, "methods", None)
        methods: set[str] = set(raw_methods or set())
        if not methods:
            continue
        raw_path: Any = getattr(route, "path", None) or getattr(
            route, "path_format", ""
        )
        path = str(raw_path)
        entries.append((frozenset(methods), path))
    return entries


def test_sem_prefixo_duplo_nem_handler_duplicado() -> None:
    """Nenhum path com /api/v1/api/v1; nenhum (method,path) duplicado."""
    routes = _http_routes()
    assert routes, "app sem rotas HTTP?"
    doubled = sorted({path for _, path in routes if "/api/v1/api/v1" in path})
    assert not doubled, f"duplo prefixo /api/v1/api/v1: {doubled}"
    counts = Counter(routes)
    dups = sorted(
        f"{sorted(methods)} {path} x{count}"
        for (methods, path), count in counts.items()
        if count > 1
    )
    assert not dups, f"handlers duplicados (method,path): {dups}"


def test_todo_path_http_api_sob_api_v1() -> None:
    """Todo path HTTP de API começa com /api/v1 (exceto sistema/docs/ws)."""
    routes = _http_routes()
    assert routes, "app sem rotas HTTP?"
    offending = sorted(
        {
            path
            for _, path in routes
            if not (
                path.startswith("/api/v1")
                or path in _NON_API_PATHS
                or path.startswith("/ws")
            )
        }
    )
    assert not offending, f"paths fora de /api/v1: {offending}"
