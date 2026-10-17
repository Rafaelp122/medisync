# US-04 — Controle de Admissão, Backpressure e Fator $\alpha$

> **Tipo de Especificação:** Política de Salvaguarda e Regra de Negócio Transversal (RN05)  
> **Jornadas Vinculadas:** [`US-01 — Acolhimento e Admissão`](./US-01-acolhimento-triagem-tcle.md) e [`US-12 — Parametrização do Plantão`](./US-12-parametrizacao-politicas-plantao.md)  
> **Requisito Base:** RF-04  
> **Invariantes Relacionadas:** RN05 (Cota Diária, Capacidade Estocástica e Transbordo)  
> **Personas:** Juliana Silva (Paciente) e Carlos Drumond (Diretor Clínico)  
> **Módulos:** `queue`, `telemetry`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da Regra (User Voice)

**Como** diretor clínico da unidade de pronto-atendimento (Carlos Drumond),  
**Quero** que a plataforma controle automaticamente a admissão de novos pacientes com base na cota diária autorizada e na capacidade estocástica da equipe médica restante ($\alpha \in [1{,}20; 1{,}30]$),  
**Para que** a unidade não aceite mais pacientes do que é capaz de atender com segurança dentro do SLA contratual e não sobrecarregue os médicos plantonistas.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Admissão autorizada dentro da capacidade operacional
- **Dado que** o total de atendimentos do dia é inferior à cota diária autorizada para a unidade,
- **E** a estimativa de tempo de espera com margem de segurança $\alpha = 1{,}25$ é menor ou igual ao tempo restante do turno:
  $$\frac{\text{Pacientes Aguardando} \times \text{TMA} \times 1{,}25}{\text{Médicos Ativos}} \le \text{Tempo Restante}$$
- **Quando** um paciente solicita admissão na unidade,
- **Então** o sistema autoriza o ingresso do atendimento na fila virtual,
- **E** atualiza atomicamente o contador diário de atendimentos da unidade.

### Cenário 2: Bloqueio por atingimento da Cota Diária Máxima
- **Dado que** a unidade atingiu o limite máximo da cota diária de atendimentos autorizados,
- **Quando** um novo paciente tenta se admitir,
- **Então** o sistema rejeita a requisição preventivamente informando serviço temporariamente indisponível (HTTP 503 Service Unavailable),
- **E** emite o evento de saturação e transbordo operacional (`QUEUE_OVERFLOW_TRANSIT`),
- **E** exibe orientação clara instruindo a busca por unidade de atendimento presencial ou retorno no próximo turno.

### Cenário 3: Bloqueio preventivo por extrapolação da capacidade estocástica ($\alpha$)
- **Dado que** restam 60 minutos de plantão, com 2 médicos ativos e TMA médio de 15 minutos,
- **E** já existem 10 pacientes aguardando na fila, resultando em:
  $$\frac{10 \times 15 \times 1{,}25}{2} = 93{,}75\text{ minutos} > 60\text{ minutos}$$
- **Quando** um novo paciente tenta entrar na fila,
- **Então** o serviço barra a admissão com HTTP 503, protegendo o encerramento seguro do plantão e os limites de segurança assistencial.

---

## 3. Contrato de API

* **Endpoint Afetado:** `POST /api/v1/fila/admissao`
* **Resposta em Caso de Bloqueio por Capacidade (`503 Service Unavailable`):**
  ```json
  {
    "type": "https://medisync.org/errors/capacidade-esgotada",
    "title": "Capacidade Máxima de Atendimento Atingida",
    "status": 503,
    "detail": "A unidade atingiu o limite de capacidade operacional para o plantão atual. Busque uma unidade física ou retorne no próximo turno.",
    "instance": "/api/v1/fila/admissao"
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Cota Diária Atômica:** Chave Valkey `queue:admissoes:{org}:{today}` consultada e incrementada atomicamente (`src/modules/queue/application/services/controle_admissao_service.py`).
- [x] **Fórmula Estocástica $\alpha$:** Avaliação de $\alpha \in [1{,}20; 1{,}30]$ implementada em `ControleAdmissaoService.avaliar_capacidade()`.
- [x] **Evento de Transbordo:** Emissão de `QUEUE_OVERFLOW_TRANSIT` disparada ao exceder limites.
- [x] **Testes Automatizados:**
  - `tests/unit/test_controle_admissao.py`
  - `tests/unit/test_queue_cota_diaria.py`
  - `tests/integration/test_queue_admission_backpressure.py`
