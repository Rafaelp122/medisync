# US-13 — Telemetria Operacional e Painel do Plantão (Read Model CQRS)

> **Requisito Base:** RF-10  
> **Invariantes Relacionadas:** RNF-10 (Latência de Telemetria < 5s), Metas SMART 1 a 5  
> **Persona:** Carlos Drumond (Diretor Clínico e Gestor Operacional)  
> **Módulos:** `telemetry`  
> **Status de Qualidade:** 🟢 **Conforme** *(Com ajuste de TTL de 15s para 5s - NC-TEL-01)*

---

## 1. Narrativa da História (User Voice)

**Como** diretor clínico e gestor da unidade (Carlos Drumond),  
**Quero** visualizar em tempo real um painel consolidado com os principais indicadores operacionais (TME geral e por nível 1..5, TMA real médio e por médico, taxa de cumprimento de SLA $\ge 95\%$ e taxas de no-show/abandono),  
**Para que** eu tome decisões imediatas de reforço de escala médica e garanta a segurança assistencial sem onerar o banco de escrita transacional.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Consulta do Painel com métricas consolidadas (Caso Feliz)
- **Dado que** o plantão possui atendimentos em andamento, concluídos e ausências registradas,
- **Quando** o gestor acessa o painel operacional em `GET /api/v1/telemetria/painel`,
- **Então** o sistema apresenta os indicadores consolidados de desempenho:
  1. Tempo Médio de Espera (TME) geral e estratificado pelos 5 níveis de triagem;
  2. Tempo Médio de Atendimento (TMA) real geral e detalhado por médico plantonista;
  3. Índice percentual de cumprimento de SLA da unidade ($\ge 95\%$);
  4. Índices percentuais de ausência (no-show) e de desistências voluntárias;
- **E** responde com tempo de resposta em tempo hábil para monitoramento operacional (< 100ms em cache).

### Cenário 2: Verificação do indicador de conformidade de SLA (Meta SMART 1)
- **Dado que** o percentual de consultas atendidas dentro do tempo limite da triagem é de $96{,}2\%$,
- **Quando** o painel é consultado,
- **Então** o indicador de conformidade de SLA retorna positivo (`sla_em_conformidade = true`), sinalizando estabilidade da unidade.
- **Dado que** a demanda excedeu a capacidade e a taxa de cumprimento caiu para $91{,}0\%$,
- **Então** o indicador retorna negativo (`sla_em_conformidade = false`), disparando sinalização visual de alerta no dashboard gerencial.

---

## 3. Contrato de API

* **Endpoint:** `GET /api/v1/telemetria/painel`
* **Headers:** `Authorization: Bearer <jwt_admin_ou_medico>`, `X-Tenant-ID: <org_id>`
* **Resposta Esperada (`200 OK`):**
  ```json
  {
    "organizacao_id": 1,
    "data_referencia": "2026-10-17",
    "total_atendimentos_dia": 42,
    "tme_geral_segundos": 412,
    "tme_por_nivel": {
      "1": 45,
      "2": 180,
      "3": 450,
      "4": 920,
      "5": 1200
    },
    "tma_medio_segundos": 780,
    "tma_por_medico": {
      "018f3a5b-...": 750
    },
    "sla_cumprimento_percentual": 96.5,
    "sla_em_conformidade": true,
    "total_no_shows": 2,
    "taxa_no_show_percentual": 4.76
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Read Model Desacoplado:** Leitor puro SQL com queries agregadas assíncronas (`src/modules/telemetry/infrastructure/telemetry_reader_sql.py`).
- [x] **Cache Volátil no Valkey:** Caching de telemetria para garantir alta performance sem onerar o Postgres (`src/modules/telemetry/application/services/telemetry_service.py`).
- [ ] **Ajuste de TTL (NC-TEL-01):** Reduzir `_CACHE_TTL_SEGUNDOS` de 15s para 5s para cumprir RNF-10 e Meta SMART 5 (Objeto da Issue #76).
- [x] **Apresentação:** Router fino `telemetry_router.py` montado em `/api/v1/telemetria/painel`.
- [x] **Testes Automatizados:**
  - `tests/unit/test_telemetry_service.py`
  - `tests/unit/test_telemetry_infra.py`
  - `tests/integration/test_telemetry_router.py`
