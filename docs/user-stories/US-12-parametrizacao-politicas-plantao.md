# US-12 — Parametrização Dinâmica de Políticas de Plantão

> **Requisito Base:** RF-09  
> **Invariantes Relacionadas:** RN05 (Margem Estocástica $\alpha$), PREM-03  
> **Persona:** Carlos Drumond (Diretor Clínico e Gestor Operacional)  
> **Módulos:** `telemetry`, `queue`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** diretor clínico da unidade (Carlos Drumond),  
**Quero** configurar dinamicamente os parâmetros operacionais do plantão (cota diária máxima, quantidade de médicos ativos, fator de segurança $\alpha \in [1{,}20; 1{,}30]$, meta de TMA e tolerância de SLA),  
**Para que** a unidade se adapte rapidamente a variações sazonais de demanda (ex: surtos gripais) sem necessidade de reimplantação ou alteração de código.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Atualização dos parâmetros do plantão com sucesso (Caso Feliz)
- **Dado que** estou autenticado como gestor clínico da unidade (`Role.GESTOR_UNIDADE` / `Permission.TMA_CONFIG`),
- **Quando** envio uma requisição `PUT /api/v1/telemetria/config-plantao` com novos valores de cota diária (ex: 250), fator `alpha_backpressure = 1.25`, `tma_padrao_segundos = 720`, `tempo_tolerancia_ring_segundos = 45` e `medicos_ativos_planejados = 5`,
- **Então** o sistema valida que os valores atendem os limites operacionais permitidos ($1{,}20 \le \alpha \le 1{,}30$, `tma_padrao_segundos >= 60`, `tempo_tolerancia_ring_segundos >= 10` e `medicos_ativos_planejados >= 1`),
- **E** atualiza os parâmetros operacionais da unidade com efeito imediato nas novas admissões, estimativas de espera e janela de ring via `ShiftPolicyReaderPort`,
- **E** renova o cache de telemetria operacional,
- **E** retorna confirmação de atualização (HTTP 200 OK) com os parâmetros consolidados.

### Cenário 2: Rejeição de valores fora dos limites ou payloads parciais (HTTP 422)
- **Dado que** o gestor tenta configurar `alpha_backpressure = 1.10` (abaixo do piso de $1{,}20$), `medicos_ativos_planejados = 0`, ou submete um payload parcial omitindo qualquer um dos 11 campos obrigatórios do `PUT`,
- **Quando** submete a alteração,
- **Então** o sistema rejeita a alteração por violação de regra de negócio ou schema obrigatório (HTTP 422 Unprocessable Entity),
- **E** preserva integralmente a configuração anterior sem sobrescrita silenciosa.

---

## 3. Contrato de API

* **Consulta:** `GET /api/v1/telemetria/config-plantao`
* **Atualização:** `PUT /api/v1/telemetria/config-plantao` (todos os 11 campos obrigatórios, sem defaults no schema)
* **Headers:** `Authorization: Bearer <jwt_gestor>` (`Role.GESTOR_UNIDADE` ou `Permission.TMA_CONFIG`)
* **Payload de Atualização (`ConfigPlantaoRequest`):**
  ```json
  {
    "medicos_ativos_planejados": 5,
    "alpha_backpressure": "1.25",
    "cota_diaria_maxima": 250,
    "tma_padrao_segundos": 720,
    "tempo_tolerancia_ring_segundos": 45,
    "modo_operacao": "SUS",
    "sla_minutos_nivel_1": 0,
    "sla_minutos_nivel_2": 10,
    "sla_minutos_nivel_3": 60,
    "sla_minutos_nivel_4": 120,
    "sla_minutos_nivel_5": 240
  }
  ```
* **Resposta Esperada (`200 OK` — `ConfigPlantaoResponse`):** Retorna o registro completo atualizado com `criado_em`, `atualizado_em` (UTC) e `atualizado_por_id`.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo & Provisionamento Atômico:** Entidade rica `ConfiguracaoPlantao` (`src/modules/telemetry/domain/models.py`) e `SqlConfigPlantaoRepository.obter_ou_criar_padrao()` com `INSERT ... ON CONFLICT (singleton_guard) DO NOTHING` (`src/modules/telemetry/infrastructure/config_plantao_repository.py`).
- [x] **Entrada Direta sem Mapper Hell (ADR-008):** `ConfigPlantaoService.atualizar_configuracao` recebe `ConfigPlantaoInput` (`src/modules/telemetry/application/dtos.py`) diretamente de `ConfigPlantaoRequest` (sem `ConfigPlantaoCommand`/`to_command()`).
- [x] **Consumo Desacoplado em `queue`:** `ShiftPolicyReaderPort` (`src/modules/queue/application/ports/shift_policy_reader_port.py`) adaptada por `TelemetryShiftPolicyReaderAdapter` (`src/modules/queue/composition.py`) sobre `src/modules/telemetry/composition.py:ler_politica_plantao_snapshot` alimenta admissão, estimativa de espera e TTL de ring em `FilaService` em modo read-only.
- [x] **Migration Alembic:** Tabela singleton `configuracoes_plantao` criada em plataforma única (`migrations/versions/0001_initial_schema.py`).
- [x] **Apresentação:** Router fino `telemetry_router.py` montado em `/api/v1/telemetria/config-plantao` com schemas `ConfigPlantaoRequest` (11 campos obrigatórios) / `ConfigPlantaoResponse` (`src/modules/telemetry/presentation/schemas.py`).
- [x] **Testes Automatizados:**
  - `tests/unit/test_telemetry_model.py`
  - `tests/unit/test_telemetry_service.py`
  - `tests/unit/test_telemetry_infra.py`
  - `tests/integration/test_telemetry_router.py`
