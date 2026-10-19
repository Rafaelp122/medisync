---
name: medisync-issue-creator
description: Formalização de necessidades e gestão de escopo em dois eixos ortogonais (Diagnóstico & Impacto vs YAGNI & Guardrails) via subagentes paralelos. Transforma ideias, bugs e débitos em issues canônicas blindadas contra scope creep antes do planejamento.
---

# MediSync Issue Creator: Formalização em Dois Eixos & Gestão de Escopo

Este procedimento padroniza a transformação de necessidades espontâneas, descobertas durante o desenvolvimento, ideias ou relatos de bugs em **Issues canônicas, estruturadas e auditáveis**, operando sob **dois eixos ortogonais com subagentes paralelos**.

**Regra Fundamental:** No MediSync Express, nenhum código e nenhum plano técnico é iniciado sem uma Issue formal previamente registrada. Todo commit ou PR deve responder a um número de issue (`Fixes #xyz`).

---

## 1. Princípios da Formalização em Dois Eixos

1. **Separação Cognitiva de Fases:** Problematizar (Issue Creator) $\neq$ Arquitetar (Issue Planner) $\neq$ Auditar (PR Auditor). Misturar as três fases gera alucinação, código desnecessário e violação de contratos.
2. **Dois Eixos Ortogonais de Análise:**
   - **Eixo A (Diagnóstico & Impacto):** Qual a dor real, regras clínicas (CFM/LGPD), User Stories e blast radius nos módulos?
   - **Eixo B (Cético YAGNI & Guardrails):** O que está terminantemente FORA do escopo? Quais refatorações oportunas devem ser proibidas? Qual é o critério mínimo estrito de aceitação?
   - *Regra de Ouro:* Uma boa issue não é definida apenas pelo que se quer fazer, mas pela clareza do que **NÃO** se deve fazer.
3. **Isolamento de Contexto via Subagentes Paralelos:** Os dois eixos rodam concorrentemente para que a empolgação da solução não contamine a disciplina dos guardrails de escopo.

---

## 2. Processo Operacional em 4 Fases

### Fase 1: Triagem & Enquadramento da Demanda

Classifique a demanda em uma das tipologias canônicas:
- `[Feature]`: Nova funcionalidade clínica, operacional ou de produto.
- `[Bugfix]`: Desvio de comportamento em relação a regras canônicas ou falhas em tempo de execução.
- `[Refactor]`: Melhoria estrutural de código existente sem alteração de comportamento externo.
- `[DX/Tooling]`: Automações, scripts de desenvolvimento, justfile, CI/CD, infraestrutura ou ambiente local.
- `[Security/Compliance]`: Ajustes de auditoria, criptografia, autenticação, LGPD ou CFM.

---

### Fase 2: Disparo de Subagentes Paralelos (Os Dois Eixos)

Dispare dois subagentes concorrentes em modo *read-only* utilizando `invoke_subagent` com `TypeName="research"`:

#### 🅰️ Subagente 1 — Eixo Diagnóstico & Blast Radius
Configuração: `TypeName="research"`, `Role="Diagnóstico & Blast Radius"`
Prompt do subagente:
- Investigar o contexto do problema, sintomas, logs ou motivação funcional respondendo:
  - *Qual a dor ou oportunidade real?* (Evitar soluções antes de entender a causa raiz).
  - *Qual o valor gerado?* (Elimina débito técnico? Reduz latência? Cumpre requisito legal?).
  - *Qual o comportamento atual vs. comportamento esperado?*
- Mapear quais regras canônicas (`RNxx`), User Stories (`docs/user-stories/`) e normas regulatórias (CFM nº 2.314/2022, LGPD Art. 11) são afetadas.
- Mapear o *Blast Radius* no código: quais bounded contexts em `src/modules/` e quais ADRs (`docs/adrs/`) são impactados:
  - *ADR-001 / ADR-008:* A demanda impacta o modelo hexagonal sem mapper hell?
  - *ADR-002:* Envolve concorrência de fila, pontuação Valkey ZSET ou locks atômicos?
  - *ADR-003:* Toca em persistência, dados sensíveis com isolamento multi-tenant (RLS/OrgID)?
  - *ADR-004:* Exige processamento assíncrono em segundo plano via worker ARQ?
  - *ADR-006:* Envolve assinatura digital de prontuário/receita médica?
- Relatório esperado: Dor raiz, valor gerado, regras canônicas e módulos/ADRs afetados.

#### 🅱️ Subagente 2 — Eixo Cético YAGNI & Anti-Scope-Creep
Configuração: `TypeName="research"`, `Role="Cético YAGNI & Guardrails"`
Prompt do subagente:
- Atuar como "advogado do diabo" contra expansão descontrolada de escopo sob a premissa de *The Smallest Complete Change*:
  - Identificar e listar explicitamente tudo o que **NÃO DEVE** ser feito nesta issue (refatorações oportunistas, abstrações prematuras, telas desnecessárias, DTOs espelho intermediários).
  - **Zero Speculative Code na Origem:** Se a issue exigir novo endpoint HTTP/WS, definir o caminho canônico único (ex: `POST /api/v1/modulo/recurso`). Proibir títulos de issue que usem termos alternativos divergentes do path canônico para prevenir a criação de rotas defensivas ou aliases.
  - Delimitar os critérios de aceitação mínimos, objetivos e verificáveis (DoD preliminar).
- Relatório esperado: Lista estrita de *Out of Scope*, endpoint canônico único e critérios de aceitação.

---

### Fase 3: Síntese da Issue Canônica

O orquestrador sintetiza os relatórios no template oficial:

```markdown
# [TIPO]: Título Descritivo, Conciso e Greppável (Sem termos ambíguos)

## 1. Contexto e Motivação
Explicação clara do problema observado, oportunidade identificada ou necessidade técnica/clínica. Descrever o comportamento atual e por que a intervenção é necessária agora.

## 2. Solução Proposta (Visão de Alto Nível)
Resumo conciso da abordagem recomendada para resolver a questão, sem descer prematuramente a detalhes triviais de implementação.

## 3. Módulos & Camadas Impactadas
- **Módulos:** (ex: `src/modules/queue`, `src/core/security`)
- **Camadas Hexagonais:** (ex: `domain`, `application/services`, `infrastructure`, `presentation/routers`)
- **ADRs Aplicáveis:** (ex: ADR-001, ADR-002, ADR-008)
- **Impacto em Banco de Dados / Migrações:** (Sim/Não - Descrever brevemente)

## 4. Escopo & Não-Escopo (Guardrails Anti-Scope-Creep)
### O que FAZ parte desta issue (In Scope):
- [ ] Endpoint canônico único: `MÉTODO /api/v1/<modulo>/<recurso>` (se aplicável, com zero rotas alternativas)
- [ ] Comportamento essencial e delimitado
- [ ] Atualização da documentação Diátaxis correspondente

### O que NÃO faz parte desta issue (Out of Scope):
- 🚫 Excluir expressamente rotas defensivas, aliases ou query params especulativos
- 🚫 Excluir refatorações oportunistas não relacionadas
- 🚫 Excluir funcionalidades futuras secundárias (deixar para próxima issue)
- 🚫 Excluir abstrações prematuras, builders ou DTOs manuais intermediários

## 5. Critérios de Aceitação (DoD Preliminar)
- [ ] O comportamento X foi implementado/corrigido conforme especificação.
- [ ] Erros lançados contêm offending value e expected shape (Clean Code IA).
- [ ] Aninhamento de controle de fluxo respeita o teto de 2 níveis.
- [ ] Testes unitários novos adicionados cobrindo cenários de sucesso e erro.
- [ ] Portão completo passa com código 0 (`just check` ou `just check-fast`).

## 6. Documentação a Atualizar (Governança Diátaxis)
- [ ] `docs/explanation/domains/<contexto>-domain.md` (se envolver regras clínicas)
- [ ] `docs/how-to/<categoria>/<documento>.md` (se envolver procedimentos/tooling)
- [ ] `docs/reference/...` (se envolver novas variáveis de ambiente ou códigos RFC 7807)
```

---

### Fase 4: Registro da Issue & Transição

1. Apresentar o conteúdo formatado para aprovação do desenvolvedor.
2. Salvar o conteúdo aprovado em arquivo local temporário (ex: `issue_draft.md`).
3. Registrar a issue no repositório:
   - Se o GitHub CLI (`gh`) estiver disponível e autenticado:
     ```bash
     gh issue create --title "[TIPO]: Título" --body-file issue_draft.md
     ```
   - **Fallback Manual:** Caso o `gh` não esteja autenticado ou falhe, fornecer o markdown formatado para criação manual na interface do GitHub.
4. Remover o arquivo temporário `issue_draft.md`.
5. **Transição Automática:** Acionar imediatamente a skill [`.agents/skills/medisync-issue-planner`](../medisync-issue-planner/SKILL.md) para planejar o fatiamento TDD Inside-Out da nova issue registrada.
