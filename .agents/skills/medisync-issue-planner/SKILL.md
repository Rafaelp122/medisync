---
name: medisync-issue-planner
description: Planejamento técnico em dois eixos (Standards & Arquitetura vs Spec & Diátaxis), fatiamento TDD Inside-Out e aplicação da Menor Alteração Completa. Use sempre que iniciar a resolução de uma issue.
---

# MediSync Issue Planner: Planejamento em Dois Eixos & TDD Desacoplado em Pares

Este procedimento padroniza o ciclo de planejamento de engenharia no MediSync Express. Nenhuma linha de código de produção deve ser escrita sem que esta skill seja executada e o plano aprovado pelo usuário.

---

## 1. Princípios Fundamentais

1. **Separação Rígida entre Planejamento e Ação:** Pensar é barato; reescrever código desalinhado custa tokens, tempo e introduz bugs.
2. **Dois Eixos Ortogonais de Planejamento:**
   - **Eixo A (Standards & Arquitetura):** Mapeamento de precedentes, Fakes tipados existentes em `tests/doubles.py`, isolamento no `tach.toml`, routers finos e ADRs.
   - **Eixo B (Spec, Diátaxis & Contratos):** Mapeamento das regras canônicas, redação antecipada da documentação viva em `docs/` e definição prévia da matriz de testes.
3. **Menor Alteração Completa (The Smallest Complete Change):**
   - O melhor plano é aquele que resolve 100% da issue com o menor diff possível, sem inventar camadas, DTOs espelho manuais (Mapper Hell) ou opções que ninguém pediu.
4. **Desenvolvimento Desacoplado em Pares (TDD Inside-Out):**
   - O teste (Red) é concebido estritamente a partir da Spec; o código (Green) é implementado exclusivamente para satisfazer o teste sem *Speculative Generality*.
5. **Documentação é Entregável de Primeira Classe:** Nenhuma feature é concluída sem documentação Diátaxis atômica no mesmo ciclo.

---

## 2. Processo Operacional em 4 Fases

### Fase 1: Triagem, Fixação da Issue & Grep de Chamadores

1. Obtenha a issue oficial registrada:
   ```bash
   gh issue view <numero> --json title,body
   ```
2. Isole as restrições:
   - Quais critérios estão no **In Scope**?
   - Quais comportamentos estão expressamente proibidos no **Out of Scope**?
   - Quais regras clínicas (`RNxx`), normas CFM/LGPD e User Stories governam a demanda?
3. **Paridade Estrita de Contratos & Zero Speculative Code (Never Code Around Ambiguity):**
   - Identifique nominalmente cada endpoint HTTP/WS e método de serviço solicitado na Issue.
   - **Proibido:** Propor rotas alternativas, aliases defensivos, parâmetros opcionais redundantes ou fallbacks especulativos para acomodar termos divergentes em narrativas. Toda ação tem exatamente 1 contrato canônico. Em caso de discrepância entre título e corpo da issue, liste em `Open Questions` para aprovação do usuário antes de desenhar o plano.
4. **Grep Every Caller (Mapeamento de Regressão Silenciosa):**
   - Se a demanda alterar a assinatura, retorno ou comportamento de qualquer função existente, execute uma busca global no terminal (`grep_search` ou `rg`) para mapear previamente todos os pontos de consumo que precisarão ser ajustados.

---

### Fase 2: Pesquisa em Dois Eixos via Subagentes Paralelos

Dispare dois subagentes concorrentes em modo *read-only* utilizando `invoke_subagent` com `TypeName="research"`:

#### 🅰️ Subagente 1 — Eixo Standards & Arquitetura
Configuração: `TypeName="research"`, `Role="Pesquisa Standards & Arquitetura"`
Prompt do subagente:
- Varrer o repositório para mapear precedentes técnicos:
  - Quais Fakes e test doubles em `tests/doubles.py` já atendem à demanda (`FakeAsyncSession`, `FakeValkey`, etc.)?
  - Quais camadas e regras de importação no `tach.toml` devem ser respeitadas?
  - Como o Composition Root (`composition.py`) do módulo deve orquestrar a injeção de dependências sem expor infraestrutura aos routers?
  - Identificar oportunidades de reuso para evitar duplicação ou wrappers desnecessários.
- Relatório esperado: Precedentes de doubles, portas e dependências do Tach.

#### 🅱️ Subagente 2 — Eixo Spec, Diátaxis & Matriz de Testes
Configuração: `TypeName="research"`, `Role="Pesquisa Spec & Diátaxis"`
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

## 1. Alinhamento Arquitetural & Menor Alteração Completa
- A Menor Alteração Completa: o que podemos reutilizar (stdlib, doubles existentes, helpers) em vez de criar código novo?
- Camadas impactadas e garantia de portas/DTOs imutáveis.
- Garantia de routers finos (zero DB, zero commit no router).
- Schemas com `from_attributes = True` (zero mapper hell).
- Test doubles canônicos mapeados em `tests/doubles.py`.
- Resultado do "Grep Every Caller": lista de arquivos chamadores a ajustar.

## 2. Governança de Documentação Diátaxis (Obrigatório)
Listar explicitamente quais arquivos devem ser atualizados/criados:
- [ ] `docs/explanation/domains/<dominio>-domain.md`: Adicionar RN-xx.
- [ ] `docs/user-stories/US-xx-*.md`: Atualizar critérios de aceite.
- [ ] `docs/reference/...`: Atualizar se houver novas variáveis ou erros.

## 3. Matriz de Testes Previstos (Critérios de Aceite Red)
- [ ] `test_<cenario_sucesso>`: Comportamento esperado e commit único.
- [ ] `test_<cenario_erro_ofensivo>`: Lançamento de exceção rica contendo offending value.
- [ ] `test_<cenario_borda_ou_concorrencia>`: Idempotência, locks ou race conditions.

## 4. Fatiamento em Tarefas Atômicas (TDD Inside-Out)

### Camada 1: Domínio & Validações Puras (Entidades Ricas & Exceptions)
- **Red:** Escrever `tests/unit/test_<modulo>_models.py` validando invariantes e mensagens com offending value. Executar e comprovar FALHA (Red).
- **Green:** Implementar entidade rica em `domain/models.py` e exceção em `domain/exceptions.py`. Executar `just test-fast` e comprovar SUCESSO (Green).

### Camada 2: Aplicação, Portas & Fakes (Services & Ports)
- **Red:** Escrever `tests/unit/test_<modulo>_service.py` usando `FakeAsyncSession` e Fakes de `tests/doubles.py`. Comprovar FALHA (Red).
- **Green:** Implementar `application/dtos.py`, `ports/` e `services/` (commit único, docstrings de proveniência 3-5 linhas). Executar `just test-fast` e `just typecheck` e comprovar SUCESSO (Green).

### Camada 3: Apresentação & Router Fino (Routers & Schemas)
- **Red:** Escrever `tests/unit/test_<modulo>_router.py` cobrindo endpoints HTTP/WS e status codes. Comprovar FALHA (Red).
- **Green:** Implementar `presentation/schemas.py`, `presentation/dependencies.py` e `presentation/routers/`. Executar `just test-fast` e `tests/architecture/test_routers_are_thin.py` e comprovar SUCESSO (Green).

### Camada 4: Documentação Diátaxis & Quality Gate
- Atualizar arquivos de documentação conforme Seção 2.
- Executar portão unificado: `just check` (ou `just check-fast`).
```

---

## 3. Fase 4: Checkpoint de Aprovação & Transição para Revisão

1. **Parada Obrigatória:** Ao finalizar o `implementation_plan.md`, defina `RequestFeedback: true` no metadata e **AGUARDE** aprovação explícita do usuário antes de criar código.
2. **Execução Fiel ao Plano (Prompt-to-Plan Binding):**
   - Conduza as fatias TDD Inside-Out estritamente conforme o plano aprovado. É terminantemente proibido injetar rotas, aliases, fallbacks ou parâmetros não previstos no plano.
   - **Proporcionalidade Operacional:** Em demandas pontuais ou correções de pequeno/médio porte, o próprio agente orquestrador pode executar as camadas TDD diretamente na sessão (Red $\to$ Green), sem a necessidade de despachar múltiplos subagentes. Caso opte por despachar subagentes executores, utilize `TypeName="self"` (com permissões completas de escrita e comando).
3. **Entrega e Segregação de Funções (Anti-Self-Audit):** Ao concluir o desenvolvimento com `just check` verde e `walkthrough.md` gerado:
   - **Proibido Auto-Auditoria:** O agente de implementação **NÃO DEVE** executar a revisão nesta mesma sessão para evitar viés de confirmação e contaminação de contexto.
   - O agente encerra seu ciclo de trabalho orientando o usuário a abrir uma **nova sessão limpa (zero-context)** para executar a skill [`.agents/skills/medisync-pr-review`](../medisync-pr-review/SKILL.md) de forma independente e imparcial.
