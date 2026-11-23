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
- **Dado que** a unidade atingiu o limite máximo da cota diária autorizada em `ConfiguracaoPlantao` (`cota_diaria_maxima`),
- **Quando** um novo paciente tenta se admitir,
- **Então** a reserva atômica em `ValkeyQueueEngine.consumir_cota_ou_bloquear` reverte imediatamente o incremento e rejeita a requisição (HTTP 503 Service Unavailable, `code: "ADMISSAO_FILA_SUSPENSA"`),
- **E** registra log estruturado de saturação (`motivo="COTA_ATINGIDA"`),
- **E** exibe orientação clara instruindo a busca por unidade de atendimento presencial ou retorno no próximo turno.

### Cenário 3: Bloqueio preventivo por extrapolação da capacidade estocástica ($\alpha$)
- **Dado que** restam 60 minutos de plantão, com 2 médicos ativos em `plantao:medicos_ativos` e TMA de 15 minutos,
- **E** já existem 10 pacientes aguardando na fila, resultando em:
  $$\frac{10 \times 15 \times 1{,}25}{2} = 93{,}75\text{ minutos} > 60\text{ minutos}$$
- **Quando** um novo paciente tenta entrar na fila,
- **Então** o serviço estorna a cota reservada (`estornar_cota_diaria`) e barra a admissão com HTTP 503 (`motivo="CAPACIDADE_EXCEDIDA"`), protegendo o encerramento seguro do plantão e os limites de segurança assistencial.

---

## 3. Contrato de API

* **Endpoint Afetado:** `POST /api/v1/fila/admissao`
* **Resposta em Caso de Bloqueio por Capacidade (`503 Service Unavailable`):**
  ```json
  {
    "type": "about:blank",
    "title": "Admissão na Fila Suspensa",
    "status": 503,
    "detail": "O acolhimento virtual está temporariamente suspenso no momento pois a capacidade do plantão atual foi atingida (previsão de atendimento excede o tempo de plantão restante). Por favor, procure uma unidade de atendimento presencial ou tente novamente no próximo turno.",
    "code": "ADMISSAO_FILA_SUSPENSA",
    "instance": "/api/v1/fila/admissao"
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Presença Real & Política de Plantão:** Contagem de médicos ativos lida de `plantao:medicos_ativos` via `QueueEnginePort.obter_medicos_ativos_count()` e parâmetros lidos de `ConfiguracaoPlantao` via `ShiftPolicyReaderPort` (sem confiar em `medicos_ativos` do cliente).
- [x] **Cota Diária Atômica e Estorno:** Chave Valkey `queue:admissoes:{data}` reservada atomicamente via `consumir_cota_ou_bloquear()` com estorno via `estornar_cota_diaria()` em rollback de banco (`src/modules/queue/infrastructure/valkey_queue_engine.py`, `src/modules/queue/application/services/fila_service.py`).
- [x] **Fórmula Estocástica $\alpha$:** Avaliação implementada em `avaliar_capacidade_admissao()` e `ControleAdmissaoService.avaliar_admissao()` (`src/modules/queue/application/services/controle_admissao_service.py`).
- [x] **Telemetria de Transbordo:** Log estruturado em `ControleAdmissaoService.avaliar_admissao` e exceção RFC 7807 `AdmissaoFilaSuspensaError` (HTTP 503).
- [x] **Testes Automatizados:**
  - `tests/unit/test_controle_admissao.py`
  - `tests/unit/test_queue_cota_diaria.py`
  - `tests/integration/test_queue_admission_backpressure.py`
