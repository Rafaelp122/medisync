# US-13 — Telemetria Operacional e Painel do Plantão (Read Model CQRS)

> **Requisito Base:** RF-10  
> **Invariantes Relacionadas:** RNF-10 (Latência de Telemetria < 5s), Metas SMART 1 a 5  
> **Persona:** Carlos Drumond (Diretor Clínico e Gestor Operacional) e Dr. Eduardo Rocha (Médico Plantonista)  
> **Módulos:** `telemetry`  
> **Status de Qualidade:** 🟢 **Conforme** *(Resoluções NC-TEL-01 na Issue #76, NC-TEL-02 e NC-SEC-01 na Issue #87)*

---

## 1. Narrativa da História (User Voice)

**Como** diretor clínico e gestor da unidade (Carlos Drumond),  
**Quero** visualizar em tempo real um painel consolidado com os principais indicadores operacionais (TME geral e por nível 1..5, TMA real médio e por médico, taxa de cumprimento de SLA $\ge 95\%$ e taxas de no-show/abandono),  
**Para que** eu tome decisões imediatas de reforço de escala médica e garanta a segurança assistencial sem onerar o banco de escrita transacional.

**Como** médico plantonista (Dr. Eduardo Rocha),  
**Quero** acompanhar o painel operacional de telemetria durante o plantão,  
**Para que** eu tenha visibilidade da carga da fila, tempos médios de espera e alinhamento assistencial com as metas da unidade, sem permissão para alterar as políticas de capacidade da unidade.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Consulta do Painel no Dashboard Gerencial (`/gestor`) (Caso Feliz - Issue #141 / #167)
- **Dado que** o plantão possui atendimentos em andamento, concluídos e ausências registradas,
- **E** o **Gestor da Unidade** (`Role.GESTOR_UNIDADE`) acessa a rota protegida `/gestor` (`frontend/src/routes/gestor.tsx`) via `SessionTransport.ensureStaffSession("GESTOR_UNIDADE")`, mantendo o access token exclusivamente em memória privada e reidratando-o via cookie HttpOnly silencioso no F5 (caso contrário redireciona para `/interno/login`),
- **Quando** a subárvore `PainelMetricasAoVivo` (`frontend/src/features/telemetry/components/painel/painel-metricas-ao-vivo.tsx`) consulta `GET /api/v1/telemetria/painel` via hook compartilhado `usePainelTelemetria` (`frontend/src/api/hooks/use-painel-telemetria.ts`),
- **Então** o sistema apresenta os indicadores consolidados de desempenho:
  1. Tempo Médio de Espera (TME) geral e estratificado pelos 5 níveis de triagem;
  2. Tempo Médio de Atendimento (TMA) real geral (com fallback de meta padrão de `600s` quando sem configuração prévia) e detalhado por médico plantonista;
  3. Índice percentual de cumprimento de SLA da unidade ($\ge 95\%$);
  4. Índices percentuais de ausência (no-show) e de desistências voluntárias exibidos diretamente na escala `0..100` em `TaxasOperacionaisCard`, além de **"Cota Livre SUS"** quando sem limite diário;
- **E** responde com tempo de resposta em tempo hábil para monitoramento operacional (< 100ms em cache).

### Cenário 2: Verificação do indicador de conformidade de SLA (Meta SMART 1)
- **Dado que** o percentual de consultas atendidas dentro do tempo limite da triagem é de $96{,}2\%$,
- **Quando** o painel é consultado,
- **Então** o indicador de conformidade de SLA retorna positivo (`sla_em_conformidade = true`), sinalizando estabilidade da unidade.
- **Dado que** a demanda excedeu a capacidade e a taxa de cumprimento caiu para $91{,}0\%$,
- **Então** o indicador retorna negativo (`sla_em_conformidade = false`), disparando sinalização visual de alerta no dashboard gerencial.

### Cenário 3: Consulta do Painel por Médico Plantonista e Blindagem de Configuração (NC-TEL-02)
- **Dado que** o médico plantonista Dr. Eduardo Rocha está autenticado com papel `Role.MEDICO`,
- **Quando** ele requisita a visualização do painel operacional em `GET /api/v1/telemetria/painel`,
- **Então** o sistema responde com status `200 OK` e os indicadores consolidados de telemetria da unidade;
- **Mas quando** o médico tenta consultar ou alterar parâmetros de capacidade em `GET /api/v1/telemetria/config-plantao` ou `PUT /api/v1/telemetria/config-plantao`,
- **Então** o sistema rejeita a operação com status `403 Forbidden` e envelope RFC 7807 (`code="FORBIDDEN"`) indicando o papel ofensivo `MEDICO`.

---

## 3. Contrato de API

* **Endpoint:** `GET /api/v1/telemetria/painel`
* **Query Params:** `desconsiderar_cache` (`bool`, opcional, default `false`)
* **Headers:** `Authorization: Bearer <jwt_gestor_ou_medico>` (`Role.GESTOR_UNIDADE` ou `Role.MEDICO`)
* **Resposta Esperada (`200 OK` — `PainelTelemetriaResponse`):**
  ```json
  {
    "gerado_em": "2026-11-23T13:00:00Z",
    "tme_medio_segundos": 412.0,
    "tme_nivel_1_segundos": 45.0,
    "tme_nivel_2_segundos": 180.0,
    "tme_nivel_3_segundos": 450.0,
    "tme_nivel_4_segundos": 920.0,
    "tme_nivel_5_segundos": 1200.0,
    "tma_medio_segundos": 780.0,
    "medicos_tma": [
      {
        "medico_id": "018f3a5b-0000-7000-8000-000000000001",
        "nome": "Dr. Eduardo Rocha",
        "total_atendimentos": 12,
        "tma_segundos": 750.0
      }
    ],
    "no_show_rate": 4.76,
    "evasao_rate": 1.2,
    "sla_compliance_percentual": 96.5,
    "sla_em_conformidade": true,
    "medicos_ativos_count": 3,
    "total_pacientes_fila": 4,
    "total_atendimentos": 42
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Read Model Desacoplado:** `TelemetryReaderPort` com método único `obter_painel_telemetria(config, data_inicio)` (`src/modules/telemetry/application/ports/telemetry_reader_port.py`) e leitor SQL `SqlTelemetryReader` reutilizando `config.obter_sla_segundos(1..5)` (`src/modules/telemetry/infrastructure/telemetry_reader_sql.py`).
- [x] **Cache Volátil no Valkey:** `ValkeyTelemetryCache` (`src/modules/telemetry/infrastructure/valkey_telemetry_cache.py`) serializa `PainelTelemetriaDTO` via Pydantic `TypeAdapter` sob a chave `telemetry:painel` com TTL de 5s (`TelemetryService.obter_painel`).
- [x] **Ajuste de TTL (NC-TEL-01):** TTL de 5s via injeção IoC (ADR-009) para cumprir RNF-10 e Meta SMART 5 (Resolvido na Issue #76).
- [x] **Acesso Clínico ao Painel (NC-TEL-02):** Dependência `require_telemetry_view_auth` permitindo `Role.MEDICO` e `Role.GESTOR_UNIDADE` no `GET /painel`, mantendo `config-plantao` restrito à gestão (`src/modules/telemetry/presentation/dependencies.py`).
- [x] **Segurança e Singleton Operacional (NC-SEC-01 / ADR-013):** Tabela singleton `configuracoes_plantao` (`singleton_guard IS TRUE`) e controle RBAC sem bypass global validados na suíte de integração com PostgreSQL real (`tests/integration/test_migrations.py` e `tests/integration/test_telemetry_router.py`).
- [x] **Apresentação:** Router fino `telemetry_router.py` montado em `/api/v1/telemetria/painel`.
- [x] **Frontend Rota & Painel do Gestor da Unidade (Issue #141 / #144 / #167):** Rota `/gestor` (`frontend/src/routes/gestor.tsx`) validando papel `GESTOR_UNIDADE` via `SessionTransport` (`frontend/src/lib/session-transport.ts`), polling de 5s isolado em `PainelMetricasAoVivo` (`frontend/src/features/telemetry/components/painel/painel-metricas-ao-vivo.tsx`) consumindo `usePainelTelemetria` (`frontend/src/api/hooks/use-painel-telemetria.ts`) e fallback de `600s` sem re-renderizar `ConfigPlantaoCard` ou o slot BPA-I.
- [x] **Testes Automatizados:**
  - `tests/unit/test_telemetry_service.py`
  - `tests/unit/test_telemetry_infra.py`
  - `tests/integration/test_telemetry_router.py`
