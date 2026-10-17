# US-11 — Conclusão de Atendimento e Liquidação Contábil (SUS / Particular)

> **Requisito Base:** RF-08  
> **Invariantes Relacionadas:** RN-NEG-01 (Fluxo Financeiro Não Obstrutivo)  
> **Persona:** Patrícia Mendes (Coordenadora de Faturamento e Regulação)  
> **Módulos:** `billing`, `consultation`, `queue`  
> **Status de Qualidade:** 🔴 **Não Conforme** *(NC-BIL-02 / Issue #78)*

---

## 1. Narrativa da História (User Voice)

**Como** coordenadora de faturamento hospitalar (Patrícia Mendes),  
**Quero** que a finalização da consulta médica no PEP acione automaticamente a liquidação financeira no módulo de faturamento (capturando a reserva financeira particular ou consolidando o procedimento em lote de faturamento SUS BPA/APAC),  
**Para que** a instituição não tenha perda de receita, glosas contábeis ou atendimentos médicos concluídos sem registro financeiro auditável.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Liquidação automática no perfil Particular / Cartão de Crédito
- **Dado que** o paciente realizou consulta médica sob modalidade particular com pré-autorização de cartão aprovada,
- **Quando** o médico conclui formalmente o atendimento clínico em `POST /api/v1/consultations/{id}/finalize`,
- **Então** o sistema aciona a rotina de faturamento para captura do valor aprovado,
- **E** confirma a liquidação da fatura no gateway de pagamento com status de pagamento confirmado,
- **E** disponibiliza o recibo financeiro vinculado ao prontuário do atendimento.

### Cenário 2: Consolidação em lote de faturamento SUS (BPA/APAC)
- **Dado que** o atendimento ocorreu em uma organização pública sob convênio SUS,
- **Quando** o atendimento clínico é finalizado pelo médico,
- **Então** o faturamento associa o procedimento executado (código SIGTAP de teleconsulta) ao lote de produção da unidade,
- **E** valida a consistência do Cartão Nacional de Saúde (CNS) e dados regulatórios obrigatórios,
- **E** marca a fatura SUS como consolidada em lote, pronta para exportação no faturamento do período.

### Cenário 3: Resiliência em caso de falha de captura financeira particular
- **Dado que** o gateway de pagamento particular rejeita a captura final da cobrança,
- **Quando** a rotina de faturamento tenta liquidar a transação,
- **Então** o prontuário clínico e os documentos emitidos pelo médico NÃO são bloqueados (o ato médico é preservado),
- **E** a fatura é registrada com status de pendência de regularização,
- **E** o paciente é notificado para atualizar o método de pagamento sem prejuízo à sua receita médica.

---

## 3. Contrato de API Esperado (Gap da Issue #78)

* **Disparo Automático:** Invocado internamente na conclusão do prontuário eletrônico.
* **Consulta de Faturas:** `GET /api/v1/billing/atendimentos/{atendimento_id}/fatura`
  *Resposta (`200 OK`):*
  ```json
  {
    "fatura_id": "018f3a5b-...",
    "atendimento_id": "018f3a5b-...",
    "modalidade": "PARTICULAR",
    "valor_total_centavos": 15000,
    "status": "PAGA",
    "transacao_gateway_id": "tx_live_123456",
    "liquidado_em": "2026-10-17T09:45:00Z"
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [ ] **Modelo de Faturamento:** Criar entidade rica FaturaAtendimento com multi-tenant PostgreSQL RLS no pacote domain/models do módulo billing.
- [ ] **Serviço de Liquidação:** Implementar `LiquidacaoService` com suporte a SUS (SIGTAP) e Particular (`src/modules/billing/application/services/`).
- [ ] **Porta Inter-módulos:** Criar interface `LiquidacaoPort` em `consultation` para acionamento na conclusão do PEP sem acoplamento direto.
- [ ] **Composition Root de Billing:** Criar `src/modules/billing/composition.py` (resolvendo também NC-BIL-03).
- [ ] **Testes Automatizados:**
  - Criar testes unitários para o modelo de fatura.
  - Criar testes de integração para o fluxo de liquidação SUS e Particular.
