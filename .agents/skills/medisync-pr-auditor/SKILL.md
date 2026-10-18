---
name: medisync-pr-auditor
description: Auditoria hostil e verificação formal pré-merge baseada em evidências ("Evidence over Narrative"). Audita arquitetura hexagonal, routers finos, clean code para IA, testes com Fakes, rastreabilidade Diátaxis e executa o portão de qualidade completo. Use antes de aprovar PRs, concluir tarefas ou mesclar código.
---

# MediSync PR Auditor: Auditoria Hostil Baseada em Evidências

Esta skill define o protocolo de auditoria rigoroso para validação de implementações e pull requests no MediSync Express. 

---

## 1. Princípio Fundamental: Evidências sobre Narrativa

Nenhuma alegação de desenvolvedor ou subagente é tratada como verdade por padrão.
- Afirmações como *"está testado"*, *"está tipado"* ou *"passou no linter"* são nulas sem a saída do terminal comprovando o código de retorno 0.
- Qualquer desvio das regras de `AGENTS.md`, ADRs ou User Stories é **bloqueante** para aprovação.

---

## 2. Roteiro de Verificação Automatizada (Gates de Execução)

O auditor deve executar a sequência completa de comandos no terminal e inspecionar os resultados:

### Gate 1: Auditoria Estática de Clean Code para IA
```bash
just audit-ai-code
```
- **Critério de Rejeição:** Qualquer função com profundidade de aninhamento $> 2$ ou novos `raise` de exceção com strings estáticas cegas (sem *offending value*).

### Gate 2: Auditoria de Fronteiras Modulares
```bash
just tach
```
- **Critério de Rejeição:** Qualquer violação de camadas ou import cruzado de infraestrutura entre módulos.

### Gate 3: Auditoria de Integridade Documental Diátaxis
```bash
just docs-check
```
- **Critério de Rejeição:** Qualquer link relativo markdown quebrado ou bloco de código colado $> 5$ linhas.

### Gate 4: Auditoria de Segredos e Credenciais
```bash
just scan-secrets
```
- **Critério de Rejeição:** Qualquer credencial, token ou chave privada exposta no histórico git.

### Gate 5: Portão de Qualidade Completo
```bash
just check
```
- **Critério de Rejeição:** Qualquer falha em `fmt`, `lint` (Ruff), `typecheck` (`basedpyright` em modo strict), testes unitários com cobertura inferior à meta, ou testes de integração.

---

## 3. Checklist Manual de Arquitetura e Clean Code

Além dos comandos automatizados, o auditor deve inspecionar o diff (`git diff`) avaliando:

1. **Routers Finos (ADR-001 §6-§7):**
   - O router faz chamadas diretas ao banco, `commit()`, `refresh()` ou `text()`? (Se sim: **REJEITAR**).
   - O router importa `infrastructure` ou instancia services diretamente sem passar pela `composition.py`? (Se sim: **REJEITAR**).
2. **Eliminação de Mapper Hell (ADR-008):**
   - Foram criados DTOs espelho manuais com conversores `to_domain` ou `to_orm`? (Se sim: **REJEITAR**).
   - Schemas de apresentação usam `model_config = ConfigDict(from_attributes=True)` e validação direta?
3. **Qualidade dos Testes (Named Fakes vs Anonymous Mocks):**
   - Os novos testes unitários abusam de `MagicMock()`, `patch()` ou `cast("Any", ...)` onde cabiam os fakes tipados de `tests/doubles.py` (`FakeAsyncSession`, `FakeMemoryStorage`, `FakePDFGenerator`, `FakeArqPool`)? (Se sim: **EXIGIR REFATORAÇÃO**).
4. **Docstrings de Proveniência (Lean):**
   - Métodos públicos de services contêm docstrings enxutas de 3 a 5 linhas apontando para as regras canônicas (`Regras: docs/...`) sem repetir `Args:` e `Returns:` já tipados?
5. **Aderência à User Story:**
   - A entrega atende integralmente aos critérios de aceite da User Story canônica em `docs/user-stories/`?

---

## 4. Emissão do Relatório de Auditoria

Ao concluir a análise, o auditor deve emitir o parecer final no seguinte formato:

```markdown
### 📋 Relatório de Auditoria Hostil de PR

| Item Auditado | Status | Evidência / Observação |
|---|:---:|---|
| **Clean Code AST (`just audit-ai-code`)** | PASS / FAIL | Zero aninhamento > 2, exceções ricas |
| **Fronteiras Tach (`just tach`)** | PASS / FAIL | Todos os módulos validados |
| **Documentação Diátaxis (`just docs-check`)** | PASS / FAIL | Zero links quebrados |
| **Varredura de Segredos (`just scan-secrets`)** | PASS / FAIL | Zero leaks detectados |
| **Portão Completo (`just check`)** | PASS / FAIL | Testes, types (strict) e linter verdes |
| **Routers Finos & Mapper Hell** | PASS / FAIL | Conformidade com ADR-001 e ADR-008 |
| **Testes com Fakes Tipados** | PASS / FAIL | Uso canônico de tests/doubles.py |
| **Aderência à User Story** | PASS / FAIL | Atendimento aos critérios de aceite |

**Veredito:** [APROVADO PARA MERGE] ou [REPROVADO COM PENDÊNCIAS]

*(Se reprovado, listar os arquivos, linhas exatas e comando de correção necessário)*
```
