---
name: medisync-issue-creator
description: Procedimento obrigatório para transformar necessidades espontâneas, ideias fora do plano, débitos técnicos, bugs ou novas features em uma Issue canônica, estruturada e rastreável antes do planejamento e implementação.
---

# MediSync Issue Creator: Formalização de Necessidades e Gestão de Escopo

Este procedimento padroniza a transformação de necessidades espontâneas, descobertas durante o desenvolvimento, ideias fora dos planos ou relatos de bugs em **Issues canônicas, estruturadas e auditáveis**.

**Regra Fundamental:** No MediSync Express, nenhum código e nenhum plano técnico é iniciado sem uma Issue formal previamente registrada. Todo commit ou PR deve responder a um número de issue (`Fixes #xyz`).

---

## 1. Princípios da Formalização

1. **Separação Cognitiva de Fases:** Problematizar (Issue Creator) $\neq$ Arquitetar (Issue Planner) $\neq$ Auditar (PR Auditor). Misturar as três fases gera alucinação, código desnecessário e violação de contratos.
2. **Filtro YAGNI & Não-Escopo:** Toda issue deve declarar com a mesma ênfase o que **ESTÁ** no escopo e o que **NÃO ESTÁ** no escopo, prevenindo *scope creep*.
3. **Conformidade Regulatória Precoce:** Sendo um sistema de saúde, alterações não mapeadas podem quebrar conformidade CFM (Res. 2.314/2022) ou LGPD (Art. 11). A issue já identifica se há impacto regulatório.
4. **Rastreabilidade Modular & ADRs:** A issue deve apontar previamente quais módulos (`src/modules/*`) e decisões arquiteturais (`docs/adrs/`) são tocados.

---

## 2. Fase 1: Diagnóstico e Enquadramento da Necessidade

Ao receber o relato da necessidade pelo desenvolvedor, o agente deve classificar e responder internamente:

### 1. Tipologia da Demanda:
- `[Feature]`: Nova funcionalidade clínica, operacional ou de produto.
- `[Bugfix]`: Desvio de comportamento em relação a regras canônicas ou falhas em tempo de execução.
- `[Refactor]`: Melhoria estrutural de código existente sem alteração de comportamento externo.
- `[DX/Tooling]`: Automações, scripts de desenvolvimento, justfile, CI/CD ou ambiente local.
- `[Security/Compliance]`: Ajustes de auditoria, criptografia, autenticação, LGPD ou CFM.

### 2. Perguntas-Chave de Enquadramento:
- **Qual a dor ou oportunidade real?** (Evitar soluções antes de entender a causa raiz).
- **Qual o valor gerado?** (Elimina débito técnico? Reduz latência? Cumpre requisito legal?).
- **Qual o comportamento atual vs comportamento esperado?**

---

## 3. Fase 2: Varredura de Impacto & Blast Radius (Read-Only)

Antes de redigir a issue, realize buscas atômicas rápidas (`grep_search` ou `find_by_name`):

1. **Mapeamento de Bounded Contexts:**
   - Identifique quais módulos em `src/modules/` serão afetados.
   - Verifique se a mudança afeta contratos intermodulares em `application/ports/` ou tabelas compartilhadas.
2. **Checagem de ADRs:**
   - A demanda impacta o modelo hexagonal sem mapper hell? (ADR-001 / ADR-008)
   - Envolve concorrência de fila ou locks atômicos? (ADR-002)
   - Toca em persistência ou dados sensíveis com RLS? (ADR-003)
   - Exige processamento em segundo plano? (ADR-004)
   - Envolve assinatura digital de prontuário/receita? (ADR-006)
3. **Checagem Diátaxis:**
   - Já existe documentação relacionada em `docs/explanation/domains/` ou `docs/how-to/`?

---

## 4. Fase 3: Estrutura Canônica da Issue

A issue gerada deve seguir estritamente o template abaixo:

```markdown
# [TIPO]: Título Descritivo, Conciso e Greppável

## 1. Contexto e Motivação
Explicação clara do problema observado, oportunidade identificada ou necessidade técnica/clínica. Descrever o comportamento atual e por que a intervenção é necessária agora.

## 2. Solução Proposta (Visão de Alto Nível)
Resumo conciso da abordagem recomendada para resolver a questão, sem descer prematuramente a detalhes triviais de implementação.

## 3. Módulos & Camadas Impactadas
- **Módulos:** (ex: `src/modules/identity`, `src/core/security`)
- **Camadas Hexagonais:** (ex: `domain`, `application/services`, `infrastructure`, `presentation/routers`)
- **ADRs Aplicáveis:** (ex: ADR-001, ADR-003, ADR-008)
- **Impacto em Banco de Dados / Migrações:** (Sim/Não - Descrever brevemente)

## 4. Escopo & Não-Escopo (Guardrails Anti-Scope-Creep)
### O que FAZ parte desta issue (In Scope):
- [ ] Item 1 específico e delimitado
- [ ] Item 2 específico e delimitado

### O que NÃO faz parte desta issue (Out of Scope):
- 🚫 Excluir expressamente refatorações oportunistas não relacionadas
- 🚫 Excluir funcionalidades futuras secundárias (deixar para próxima issue)

## 5. Critérios de Aceitação (DoD Preliminar)
- [ ] O comportamento X foi implementado/corrigido conforme especificação.
- [ ] Erros lançados contêm offending value e expected shape (Clean Code IA).
- [ ] Aninhamento de controle de fluxo respeita o teto de 2 níveis.
- [ ] Testes unitários novos adicionados cobrindo cenários de sucesso e erro.
- [ ] Portão completo passa com código 0 (`just check`).

## 6. Documentação a Atualizar (Governança Diátaxis)
- [ ] `docs/explanation/domains/<contexto>-domain.md` (se envolver regras clínicas)
- [ ] `docs/how-to/<categoria>/<documento>.md` (se envolver procedimentos/tooling)
- [ ] `docs/reference/...` (se envolver novas variáveis de ambiente ou códigos RFC 7807)
```

---

## 5. Fase 4: Confirmação e Registro da Issue

1. **Apresentação ao Desenvolvedor:**
   - Exiba o conteúdo formatado da issue para aprovação do usuário.
2. **Criação da Issue:**
   - Se o GitHub CLI (`gh`) estiver autenticado e configurado no ambiente, o agente pode propor executar:
     ```bash
     gh issue create --title "[TIPO]: Título" --body-file issue.md
     ```
   - Ou fornecer o markdown pronto para criação manual no repositório.
3. **Transição Automática:**
   - Uma vez registrada a issue (ex: `#102`), acionar imediatamente a skill [`.agents/skills/medisync-issue-planner`](../medisync-issue-planner/SKILL.md) para elaborar o plano técnico e fatiamento TDD.
