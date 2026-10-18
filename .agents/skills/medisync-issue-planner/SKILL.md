---
name: medisync-issue-planner
description: Procedimento obrigatório para triagem de issues, pesquisa com subagentes, elaboração de planos com documentação Diátaxis e fatiamento em tarefas atômicas orientadas a TDD. Use sempre que receber uma issue, bugfix complexo ou nova funcionalidade antes de escrever qualquer código.
---

# MediSync Issue Planner: Triagem, Pesquisa e Planejamento Orientado a TDD

Este procedimento padroniza o ciclo de planejamento de engenharia no MediSync Express. Nenhuma linha de código de produção deve ser escrita sem que esta skill seja executada e o plano aprovado pelo usuário.

---

## 1. Princípios Fundamentais

1. **Separação Rígida entre Planejamento e Ação:** Pensar é barato; reescrever código desalinhado custa tokens, tempo e introduz bugs.
2. **Evidências sobre Narrativa:** O relato da issue é uma alegação a investigar. Isole sintomas, fatos e premissas antes de propor soluções.
3. **Documentação é Entregável de Primeira Classe:** Toda alteração de regra ou contrato clínico deve ter documentação Diátaxis planejada no mesmo ciclo.
4. **TDD Atômico por Camada (Inside-Out):** Toda tarefa executável deve definir previamente seu caso de teste vermelho (Red) antes da implementação (Green).

---

## 2. Fase 1: Triagem & Coleta de Evidências

Antes de propor soluções, o agente deve auditar o contexto:
1. **Auditoria da Demanda:**
   - *O que foi observado?* (Stack trace, comportamento atual, logs).
   - *O que era esperado?* (Regra canônica do domínio ou norma regulatória CFM/LGPD).
   - *Quais bounded contexts são afetados?* (`auth`, `identity`, `triage`, `queue`, `consultation`, `billing`, `telemetry`).
2. **Consulta às Regras Canônicas:**
   - Localize o documento canônico em `docs/explanation/domains/<contexto>-domain.md`.
   - Localize as User Stories afetadas em `docs/user-stories/US-xx-*.md`.
   - Localize as decisões de arquitetura em `docs/adrs/`.

---

## 3. Fase 2: Pesquisa com Subagentes (Context Isolation)

Se a issue atender a qualquer um destes critérios:
- Afeta $\ge 3$ bounded contexts;
- Requer auditoria de migrações SQL ou RLS complexas;
- Exige rastreamento em mais de 10 arquivos;

O agente **deve** acionar um subagente de pesquisa (`invoke_subagent` com `TypeName="research"`) com instruções somente-leitura para coletar:
- Assinaturas de métodos e modelos ricos existentes.
- Fakes tipados já disponíveis em `tests/doubles.py`.
- Contratos de schemas em `presentation/schemas.py`.

---

## 4. Fase 3: Elaboração do Plano de Implementação (`implementation_plan.md`)

O artefato de plano deve residir em `implementation_plan.md` e conter obrigatoriamente:

### Estrutura Mandatória do Plano:

```markdown
# [Objetivo da Issue / Feature]

Descrição concisa do problema, diagnóstico da causa raiz e solução arquitetural.

## 1. Alinhamento Arquitetural (ADR-001 / ADR-008 / ADR-009)
- Camadas impactadas e garantia de portas/DTOs imutáveis.
- Garantia de routers finos (zero DB, zero commit no router).
- Schemas com `from_attributes = True` (zero mapper hell).

## 2. Governança de Documentação Diátaxis (Obrigatório)
Listar explicitamente quais arquivos devem ser atualizados/criados:
- [ ] `docs/explanation/domains/<dominio>-domain.md`: Adicionar RN-xx.
- [ ] `docs/user-stories/US-xx-*.md`: Atualizar critérios de aceite.
- [ ] `docs/reference/...`: Atualizar se houver novas variáveis ou erros.

## 3. Matriz de Testes Previstos (Critérios de Aceite Red)
Listar os cenários que serão escritos ANTES da implementação:
- [ ] `test_<cenario_sucesso>`: Verifica comportamento esperado e commit único.
- [ ] `test_<cenario_erro_ofensivo>`: Verifica lançamento de exceção rica contendo offending value.
- [ ] `test_<cenario_borda_ou_concorrencia>`: Verifica idempotência ou lock.

## 4. Fatiamento em Tarefas Atômicas para Subagentes (TDD Inside-Out)

Cada fatia deve ser autocontida (self-contained briefing):

### Tarefa 1: Camada de Domínio (Entidades Ricas & Exceções)
- **Red:** Criar teste em `tests/unit/test_<modulo>_models.py` validando invariantes e offending values.
- **Green:** Implementar entidade rica em `domain/models.py` e exceção em `domain/exceptions.py`.
- **Verify:** `just test-fast`.

### Tarefa 2: Camada de Aplicação (Service & Ports)
- **Red:** Criar teste em `tests/unit/test_<modulo>_service.py` usando `FakeAsyncSession` e Fakes de `tests/doubles.py`.
- **Green:** Implementar `application/dtos.py`, `ports/` e `services/` (commit único, docstrings de proveniência 3-5 linhas).
- **Verify:** `just test-fast` e `just typecheck`.

### Tarefa 3: Camada de Apresentação (Router Fino & Schemas)
- **Red:** Criar teste em `tests/unit/test_<modulo>_router.py` cobrindo endpoints HTTP/WS e status codes.
- **Green:** Implementar `presentation/schemas.py` e `presentation/routers/`.
- **Verify:** `just test-fast` e `tests/architecture/test_routers_are_thin.py`.

### Tarefa 4: Documentação Diátaxis & Portão de Qualidade
- Atualizar arquivos de documentação conforme Seção 2.
- Executar portão: `just check`, `just audit-ai-code`, `just docs-check`, `just scan-secrets`.
```

---

## 5. Fase 4: Checkpoint de Aprovação

Ao finalizar a redação do `implementation_plan.md`:
* O agente deve definir `RequestFeedback: true` no metadata do artefato.
* **PARAR IMEDIATAMENTE** e aguardar a aprovação explícita do usuário.
* É terminantemente proibido criar arquivos de código ou alterar arquivos existentes antes da aprovação do plano.
