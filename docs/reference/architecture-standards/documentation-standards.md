# Documentation Standards

> Regra atomic-denso + link-sem-cola; vale para `docs/tutorials`, `docs/how-to`, `docs/reference`, `docs/explanation/concepts`, `docs/explanation/domains`.

## Contexto

Docs desatualizam em 2 sprints quando colam código. Padrão aqui: 1 arquivo = 1 conceito testável, denso o bastante para responder sozinho, sem duplicar fonte.
Exceção: `docs/explanation/business-vision.md` e `docs/explanation/product-specification.md` continuam longos por serem documentos raiz.

## Conceito

### Tamanho atômico

- Alvo 80–250 linhas por arquivo.
- <40 linhas: funde com pai (nota fina, não navega sozinha).
- >300 linhas: quebra em 2 conceitos (vira GOD, mistura domínios).
- 1 arquivo = 1 conceito testável. Ex: fila cobre score ZSET + Lua + locks 45s + ARQ juntos; não quebrar em `score.md` + `lua.md`.

### Template obrigatório (5 seções)

```md
\# Título-conceito
\> 1 frase: o que é + onde vive
\#\# Contexto
\#\# Conceito
\#\# Onde no código
\#\# Verificação
\#\# Ver também
```

Cada seção tem um trabalho: Contexto diz quando ler; Conceito explica sem colar; Onde no código aponta; Verificação prova com comando rodável; Ver também evita fork com link.

### Formato Onde no código

Quatro prefixos, sempre `path:símbolo` + comando `rg`, nunca bloco colado:

- `Impl:` caminho do código que executa.
- `Spec:` documento ou teste que define contrato.
- `Prova viva:` teste que quebra se o conceito mudar.
- `Ver:` comando `rg` que qualquer dev roda para conferir.

Contrato colado só quando inevitável (fórmula, código `0` vs `-1`, envelope JSON): máximo 5 linhas, marcado como spec.

### Proibição de cola

- Proibido bloco `python` >5 linhas fora de `docs/reference/`.
- Proibido mesmo comando em 2 lugares; canônico mora em `how-to/`, resto referencia.
- Proibido resumir outro arquivo; fora de escopo = link relativo + 1 frase.
- Futuro MkDocs usa `pymdownx.snippets` (`--8<--`) para incluir trecho no build sem drift, sem mudar `.md` agora.

### Exemplos com fila (bom / ruim / drift)

Bom (link-sem-cola, não quebra quando Lua muda comentário):

- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua:alocar_chamada`
- Prova viva: `tests/unit/test_alocacao_service.py:test_alocar_chamada_medico_ocupado_retorna_409`
- Ver: `rg -n "alocar_chamada" src/modules/queue/infrastructure/lua/`

Ruim (cola que drifta; proibido):

- Colar os 30 linhas do `.lua` no `.md` e explicar linha a linha.
- Colar fixture `mock_valkey` + `mock_session` + `service` no tutorial; quem atualiza o service esquece o tutorial.

Drift real evitado: se doc colasse `return 0 -- médico ocupado`, e Lua trocasse `0` por `409`, doc mentiria. Com link, doc diz "código `0` = médico ocupado, `-1` = indisponível" (spec ≤5 linhas) e aponta para `alocar_chamada.lua` + `test_alocacao_service.py`, onde mudança quebra teste antes de quebrar doc.

### Rastreabilidade Bidirecional (Código ↔ Docs)

A rastreabilidade é uma via de mão dupla:
- **Dos Docs para o Código:** Feita via `Impl: src/...:símbolo` e `Prova viva: tests/...:teste`.
- **Do Código para os Docs:** Feita via **Docstrings Atômicas de Proveniência (*Lean Provenance*)** em métodos de serviços e modelos que implementam regras de negócio:
  * 3 a 5 linhas no máximo: 1 linha de intenção clínica/arquitetural + links canônicos (`Regras: docs/...`) + `Raises:` de erros de negócio.
  * Proibido duplicação de parâmetros e tipos (`Args:` e `Returns:` omitidos, pois o `basedpyright` já valida na assinatura).
  * Proibido em métodos auxiliares privados ou código trivial (zero inflação de tokens).

### Quando atualizar

- Router/composition/service/commit → `docs/how-to/backend/create-module-endpoint.md`.
- RN/score/Lua/RLS → `docs/explanation/architecture/concurrency-and-queues.md`; `concepts/` referencia.
- Novo `.env` → `docs/reference/environment/variables.md` no mesmo PR.
- Novo erro de domínio → `docs/reference/api/error-envelope.md` no mesmo PR.
- Novo padrão transversal → este arquivo.

## Onde no código

- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua:alocar_chamada`
- Prova viva: `tests/unit/test_alocacao_service.py:test_alocar_chamada_medico_ocupado_retorna_409`
- Spec: `docs/reference/index.md`
- Ver: `rg -n "alocar_chamada" src/modules/queue/infrastructure/lua/`
- Ver: `rg -n "test_alocar_chamada" tests/unit/test_alocacao_service.py`

## Verificação

```bash
wc -l docs/reference/api/error-envelope.md docs/reference/environment/variables.md docs/reference/architecture-standards/documentation-standards.md
rg -U '```python[^`]{600,}' docs/tutorials docs/how-to | head -3
rg -c "^[A-Z_]+=" .env.example
```

Esperado: cada arquivo entre 80–250 linhas; nenhum bloco python gigante em `tutorials/` ou `how-to/`; `25` vars no `.env.example` batendo com `variables.md`.

## Ver também

- [Error envelope](../api/error-envelope.md)
- [Environment variables](../environment/variables.md)
- [Create module endpoint](../../how-to/backend/create-module-endpoint.md)
- [Run tests](../../how-to/backend/run-tests.md)
- [Concurrency and queues](../../explanation/architecture/concurrency-and-queues.md)
- [Hexagonal pragmático](../../explanation/concepts/hexagonal-pragmatico.md)

### DoD docs

- [ ] 1 conceito por arquivo, 80–250 linhas (exceto business/product raiz).
- [ ] Zero código colado >5 linhas; resto `path:símbolo` + `rg` + teste-link.
- [ ] Seção `Verificação` com comando rodável.
- [ ] Links src, tests e docs referenciados existem em disco.
- [ ] `just docs-check` verde (quando wired).
