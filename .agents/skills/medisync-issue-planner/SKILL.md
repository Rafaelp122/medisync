---
name: medisync-issue-planner
description: Planejamento técnico em dois eixos (Standards & Arquitetura vs Spec & Diátaxis) e orquestração de desenvolvimento desacoplado em pares TDD (Subagente do Teste Red vs Subagente da Implementação Green). Use sempre que iniciar a resolução de uma issue.
---

# MediSync Issue Planner: Planejamento em Dois Eixos & TDD Desacoplado em Pares

Este procedimento padroniza o ciclo de planejamento de engenharia no MediSync Express. Nenhuma linha de código de produção deve ser escrita sem que esta skill seja executada e o plano aprovado pelo usuário.

---

## 1. Princípios Fundamentais

1. **Separação Rígida entre Planejamento e Ação:** Pensar é barato; reescrever código desalinhado custa tokens, tempo e introduz bugs.
2. **Dois Eixos Ortogonais de Planejamento:**
   - **Eixo A (Standards & Arquitetura):** Mapeamento de precedentes, Fakes tipados existentes em `tests/doubles.py`, isolamento no `tach.toml`, routers finos e ADRs.
   - **Eixo B (Spec, Diátaxis & Contratos):** Mapeamento das regras canônicas, redação antecipada da documentação viva em `docs/` e definição prévia da matriz de testes.
3. **Desenvolvimento Desacoplado em Pares (Two-Agent TDD Inside-Out):**
   - O agente que escreve o teste NÃO implementa a lógica do serviço. O teste (Red) é concebido a partir da Spec; o código (Green) é implementado estritamente para satisfazer o teste sem *Speculative Generality*.
4. **Documentação é Entregável de Primeira Classe:** Nenhuma feature é concluída sem documentação Diátaxis atômica no mesmo ciclo.

---

## 2. Processo Operacional em 4 Fases

### Fase 1: Triagem & Fixação da Issue

1. Obtenha a issue oficial registrada:
   ```bash
   gh issue view <numero> --json title,body
   ```
2. Isole as restrições:
   - Quais critérios estão no **In Scope**?
   - Quais comportamentos estão expressamente proibidos no **Out of Scope**?
   - Quais regras clínicas (`RNxx`), normas CFM/LGPD e User Stories governam a demanda?

---

### Fase 2: Pesquisa em Dois Eixos via Subagentes Paralelos

Dispare dois subagentes concorrentes em modo *read-only*:

#### 🅰️ Subagente 1 — Eixo Standards & Arquitetura
Prompt do subagente:
- Varrer o repositório para mapear precedentes técnicos:
  - Quais Fakes e test doubles em `tests/doubles.py` já atendem à demanda?
  - Quais camadas e regras de importação no `tach.toml` devem ser respeitadas?
  - Como o Composition Root (`composition.py`) do módulo deve orquestrar a injeção de dependências sem expor infraestrutura aos routers?
- Relatório esperado: Precedentes de doubles, portas e dependências do Tach.

#### 🅱️ Subagente 2 — Eixo Spec, Diátaxis & Matriz de Testes
Prompt do subagente:
- Mapear a documentação canônica a ser criada ou atualizada em `docs/`:
  - `docs/explanation/domains/<dominio>-domain.md` (regras `RNxx`);
  - `docs/user-stories/US-xx-*.md` (critérios de aceite BDD);
  - `docs/reference/...` (novas chaves, tabelas ou variáveis).
- Desenhar a **Matriz de Testes Red**: listar os cenários exatos de sucesso, erro com valor ofensivo e concorrência/borda que devem ser cobertos.
- Relatório esperado: Esboço Diátaxis e matriz de cenários de teste.

---

### Fase 3: Elaboração do Plano de Implementação (`implementation_plan.md`)

O orquestrador sintetiza os dois relatórios no artefato `implementation_plan.md`:

```markdown
# [Objetivo da Issue / Feature]

Descrição concisa do problema, diagnóstico da causa raiz e solução arquitetural.

## 1. Alinhamento Arquitetural (ADR-001 / ADR-008 / ADR-009)
- Camadas impactadas e garantia de portas/DTOs imutáveis.
- Garantia de routers finos (zero DB, zero commit no router).
- Schemas com `from_attributes = True` (zero mapper hell).
- Test doubles canônicos mapeados em `tests/doubles.py`.

## 2. Governança de Documentação Diátaxis (Obrigatório)
Listar explicitamente quais arquivos devem ser atualizados/criados:
- [ ] `docs/explanation/domains/<dominio>-domain.md`: Adicionar RN-xx.
- [ ] `docs/user-stories/US-xx-*.md`: Atualizar critérios de aceite.
- [ ] `docs/reference/...`: Atualizar se houver novas variáveis ou erros.

## 3. Matriz de Testes Previstos (Critérios de Aceite Red)
- [ ] `test_<cenario_sucesso>`: Comportamento esperado e commit único.
- [ ] `test_<cenario_erro_ofensivo>`: Lançamento de exceção rica contendo offending value.
- [ ] `test_<cenario_borda_ou_concorrencia>`: Idempotência, locks ou race conditions.

## 4. Fatiamento em Tarefas Atômicas para Subagentes (TDD Inside-Out)

### Camada 1: Domínio & Validações Puras (Entidades Ricas & Exceptions)
- **Subagente A (Red):** Escreve `tests/unit/test_<modulo>_models.py` validando invariantes e mensagens com offending value. Executa e comprova FALHA (Red).
- **Subagente B (Green):** Implementa entidade rica em `domain/models.py` e exceção em `domain/exceptions.py`. Executa `just test-fast` e comprova SUCESSO (Green).

### Camada 2: Aplicação, Portas & Fakes (Services & Ports)
- **Subagente A (Red):** Escreve `tests/unit/test_<modulo>_service.py` usando `FakeAsyncSession` e Fakes de `tests/doubles.py`. Comprova FALHA (Red).
- **Subagente B (Green):** Implementa `application/dtos.py`, `ports/` e `services/` (commit único, docstrings de proveniência 3-5 linhas). Executa `just test-fast` e `just typecheck` e comprova SUCESSO (Green).

### Camada 3: Apresentação & Router Fino (Routers & Schemas)
- **Subagente A (Red):** Escreve `tests/unit/test_<modulo>_router.py` cobrindo endpoints HTTP/WS e status codes. Comprova FALHA (Red).
- **Subagente B (Green):** Implementa `presentation/schemas.py`, `presentation/dependencies.py` e `presentation/routers/`. Executa `just test-fast` e `tests/architecture/test_routers_are_thin.py` e comprova SUCESSO (Green).

### Camada 4: Documentação Diátaxis & Quality Gate
- Atualizar arquivos de documentação conforme Seção 2.
- Executar portão unificado: `just check` (ou `just check-fast`).
```

---

## 3. Fase 4: Checkpoint de Aprovação & Transição para Auditoria

1. **Parada Obrigatória:** Ao finalizar o `implementation_plan.md`, defina `RequestFeedback: true` no metadata e **AGUARDE** aprovação explícita do usuário antes de criar código.
2. **Execução:** Conduza as fatias TDD Inside-Out conforme planejado.
3. **Transição Automática:** Ao concluir o desenvolvimento e ter o `just check` verde, acione a skill [`.agents/skills/medisync-pr-auditor`](../medisync-pr-auditor/SKILL.md) para a auditoria hostil pré-merge.
