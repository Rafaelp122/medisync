---
name: medisync-module-audit
description: Auditoria cirúrgica e aprofundada de um módulo hexagonal (bounded context) em repouso: integridade clínica, routers finos, conformidade Diátaxis/ADRs, concorrência e oportunidades de deleção lean.
---

# MediSync Module Audit: Auditoria Cirúrgica de Módulo Hexagonal

Esta skill define o protocolo mandatório de auditoria preventiva e cirúrgica para inspecionar um **módulo específico** (bounded context) do MediSync Express em repouso. Por focar em uma fronteira delimitada (~12 a 25 arquivos), ela elimina a saturação de contexto da IA, viabilizando uma análise profunda e livre de alucinações das 4 camadas do hexágono, de suas regras clínicas e de sua documentação viva.

---

## 1. Princípios Fundamentais

1. **O Hexágono como Unidade de Sanidade:**
   O módulo é o bounded context fechado. A auditoria deve inspecionar a coerência vertical completa entre `domain`, `application`, `infrastructure`, `presentation` e `composition.py`.
2. **Paridade 1:1 com a Documentação Diátaxis:**
   O código do módulo não existe no vácuo: ele é confrontado diretamente com o documento canônico em `docs/explanation/domains/<modulo>-domain.md` e as User Stories correspondentes em `docs/user-stories/`. O que está na doc deve estar no código; o que está no código deve estar na doc.
3. **Casos Concretos sobre Preocupações Vagas (*Evidence over Speculation*):**
   Proibido apontar gostos pessoais ou levantar conjecturas abstratas (*"no style taste, no 'consider', no vague worries"*). Todo achado deve demonstrar um cenário concreto: *"este input ou condição de corrida leva a este resultado incorreto ou quebra este contrato"*.
4. **Relatório de Diagnóstico (Read-Only):**
   Esta skill inspeciona e produz um relatório de auditoria estruturado em 4 partes. Ela **não altera código**. Os achados aprovados pelo usuário são convertidos em issues canônicas via [`.agents/skills/medisync-issue-creator`](../medisync-issue-creator/SKILL.md).

---

## 2. Processo de Auditoria em 4 Fases

### Fase 1: Fixação do Módulo & Leitura da Spec Canônica

1. **Identificar o Alvo da Auditoria:**
   - Obtenha o nome do módulo fornecido pelo usuário (ex: `queue`, `identity`, `auth`, `consultation`, `billing`, `triage`, `telemetry` ou `core`).
   - Caminho base: `src/modules/<modulo>/` (ou `src/core/` / `src/worker/` se o alvo for infraestrutura transversal).
2. **Carregar a Documentação Viva do Módulo:**
   - Leia `docs/explanation/domains/<modulo>-domain.md` (regras canônicas `RN01-RN07`).
   - Localize as User Stories governadas pelo módulo em `docs/user-stories/US-*.md`.
   - Consulte no `tach.toml` as dependências e interfaces públicas autorizadas para o módulo.
3. **Mapeamento Integral de Arquivos:**
   - Liste todos os arquivos do módulo (`find_by_name` em `src/modules/<modulo>/`).
   - Como o volume é estritamente delimitado, o auditor deve ler **todos os arquivos do módulo** antes de emitir julgamento.

---

### Fase 2: Inspeção das 4 Camadas do Hexágono (Varredura Cirúrgica)

Inspecione verticalmente cada camada contra os padrões do repositório:

#### 1. Camada de Domínio (`domain/`)
- **Entidades Ricas vs. Anêmicas (ADR-001):** As entidades SQLAlchemy (`Mapped[...]`) encapsulam regras clínicas, transições de estado e métodos de negócio, ou viraram meros sacos de dados anêmicos?
- **Invariantes e Regras Clínicas:** O cálculo de score (ex: ordenação Valkey ZSET), timestamps de antiguidade e restrições de elegibilidade atendem integralmente às regras `RNxx`?
- **Exceções com Offending Value:** Toda exceção lançada interpola o valor recebido e o valor esperado (ex.: `raise StatusInvalidoError(f"Status '{status}' inválido; esperados: {sorted(StatusAtendimento)}")`) e respeita máscara LGPD?

#### 2. Camada de Aplicação (`application/`)
- **Transação Única por Caso de Uso (ADR-001 §6):** Os métodos públicos de serviço executam `await session.commit()` exatamente uma vez no final do fluxo? Helpers e policies nunca commitam?
- **Eliminação de Mapper Hell (ADR-008):** Foram criados DTOs intermediários espelho duplicados com conversores manuais (`to_domain`/`to_orm`)? Se os dados vêm 100% do request, o schema Pydantic é usado diretamente?
- **Portas Abstratas (PEP 544):** As portas em `ports/` são puras (`typing.Protocol`), sem acoplamento a bibliotecas de infraestrutura?
- **Docstrings de Proveniência (Lean):** Métodos públicos contêm docstrings enxutas de 3 a 5 linhas apontando para `Regras: docs/...` (WHY, not WHAT)?

#### 3. Camada de Apresentação (`presentation/`)
- **Routers Finos (ADR-001 §7 / AST Guard):** Os routers têm zero chamadas ao banco, zero `commit()`, `refresh()` ou `text()`? Não importam `infrastructure` nem `models`?
- **Schemas Pydantic:** Schemas de resposta utilizam `model_config = ConfigDict(from_attributes=True)` com validação direta (`model_validate`)?
- **Anti-IDOR & Multi-Tenant:** Toda rota que recebe `{id}` valida se o recurso pertence à organização (`organizacao_id`) do usuário autenticado?
- **Tratamento de Exceções:** Routers deixam exceções de domínio subirem para os handlers do RFC 7807 (`src/core/errors.py`), usando `HTTPException` exclusivamente para rate limit ou validações de transporte?

#### 4. Camada de Infraestrutura & Injeção (`infrastructure/` e `composition.py`)
- **Isolamento de Concorrência & Cache (Valkey):** Operações de fila e concorrência utilizam comandos atômicos ou locks distribuídos?
- **Composition Root do Módulo:** A `composition.py` é o único local que instancia adaptadores de infraestrutura e orquestra a injeção via `Annotated[...Service, Depends(...)]`?
- **Configurações Desacopladas (ADR-009):** Services e domínio nunca importam `get_settings()` ou `src.core.config`? Dependências são resolvidas na composition?

#### 5. Cobertura de Testes e Fakes Tipados (`tests/`)
- Inspecione `tests/unit/test_<modulo>_*.py` e `tests/integration/`:
- Os testes utilizam os Fakes tipados oficiais de `tests/doubles.py` (`FakeAsyncSession`, `FakeValkey`, `FakeMemoryStorage`, `FakePDFGenerator`, `FakeArqPool`)?
- Há abuso de `MagicMock()`, `patch()` ou `cast("Any", ...)` onde cabiam fakes canônicos?
- A matriz de testes cobre cenários de sucesso, erro ofensivo e condições de corrida?

#### 6. Lean & Oportunidades de Deleção
- **Código Morto:** Métodos privados nunca chamados, schemas Pydantic órfãos, imports não utilizados.
- **YAGNI / Over-engineering:** Wrappers ou builders intermediários que apenas repassam chamadas sem agregar lógica.
- **Redundância:** Helpers que duplicam o que a biblioteca padrão ou o SQLAlchemy 2.0 já oferecem nativamente.

---

### Fase 3: Validação de Evidências

Antes de redigir o parecer:
- Execute `grep_search` para confirmar se símbolos apontados como "código morto" realmente não possuem chamadores em nenhum outro módulo, teste ou router.
- Valide se as fronteiras do módulo passam no `tach check`.
- Formule a menor solução definitiva para cada não-conformidade (priorizando a deleção de código).

---

### Fase 4: Emissão do Relatório de Auditoria Modular

Apresente o parecer estruturado em três níveis de severidade com achados no **formato canônico em 4 partes**:

```markdown
# 🔍 Relatório de Auditoria Modular: `<nome_do_modulo>`

**Módulo Auditado:** `src/modules/<nome_do_modulo>/`  
**Documento Canônico:** `docs/explanation/domains/<nome_do_modulo>-domain.md`  
**Fronteiras Tach:** [VÁLIDAS / DETECTADAS VIOLAÇÕES]

---

## 1. Achados de Auditoria

### 🚨 Must Fix (Críticos: Bugs Clínicos, Quebra de Transação, Routers Gordos, Falhas de Segurança)
1. **[Título Conciso do Achado]** (`src/modules/<modulo>/arquivo.py:L40-52`)
   - **O que é:** [1-2 frases explicando o código atual]
   - **Problema:** [Violação concreta de regra clínica, ADR ou bug verificável]
   - **Fix:** [A menor alteração que resolve de forma definitiva]
   - **Se ignorarmos:** [Risco assistencial, quebra de dados ou falha de conformidade]

### ⚠️ Should Fix (Importantes: Dívida Técnica, Mapper Hell, Código sem Teste, Docstring Ausente)
2. **[Título Conciso do Achado]** (`src/modules/<modulo>/arquivo.py:L110-125`)
   - **O que é:** ...
   - **Problema:** ...
   - **Fix:** ...
   - **Se ignorarmos:** ...

### 💡 Nice to Have / Oportunidades Lean (Simplificações e Deleções de Código)
3. **[Título Conciso do Achado]** (`src/modules/<modulo>/arquivo.py:L200`)
   - **O que é:** ...
   - **Problema:** ...
   - **Fix:** ...
   - **Se ignorarmos:** ...

---

## 2. Balanço Lean do Módulo
- **Linhas passíveis de deleção imediata:** ~`<N>` linhas
- **Mapeamento de DTOs / Wrappers redundantes:** `<M>` itens

---

## 3. Veredito & Transição para Ação
**Veredito:** [Saudável / Requer Correções Prioritárias nos itens 1 e 2]

**Próximo Passo:**  
Para cada achado classificado como *Must Fix* ou *Should Fix*, acione a skill [`.agents/skills/medisync-issue-creator`](../medisync-issue-creator/SKILL.md) para registrar a issue canônica com escopo YAGNI fechado e fatiamento TDD.
```

---

## 3. Auditoria do Repositório Completo (Orquestração Modular)

Caso o usuário solicite a auditoria de múltiplos módulos ou do sistema inteiro:
- **Proibido:** Fazer uma varredura única agregada e superficial de todos os arquivos simultaneamente.
- **Protocolo Correto:** O agente orquestrador deve executar o protocolo desta skill **sequencialmente, módulo por módulo** (`auth` $\to$ `identity` $\to$ `triage` $\to$ `queue` $\to$ `consultation` $\to$ `billing` $\to$ `telemetry` $\to$ `core`), emitindo o relatório granular de cada bounded context. Isso garante profundidade máxima e zero saturação de contexto.
