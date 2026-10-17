# US-12 — Parametrização Dinâmica de Políticas de Plantão

> **Requisito Base:** RF-09  
> **Invariantes Relacionadas:** RN05 (Margem Estocástica $\alpha$), PREM-03  
> **Persona:** Carlos Drumond (Diretor Clínico e Gestor Operacional)  
> **Módulos:** `telemetry`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** diretor clínico da unidade (Carlos Drumond),  
**Quero** configurar dinamicamente os parâmetros operacionais do plantão (cota diária máxima, quantidade de médicos ativos, fator de segurança $\alpha \in [1{,}20; 1{,}30]$, meta de TMA e tolerância de SLA),  
**Para que** a unidade se adapte rapidamente a variações sazonais de demanda (ex: surtos gripais) sem necessidade de reimplantação ou alteração de código.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Atualização dos parâmetros do plantão com sucesso (Caso Feliz)
- **Dado que** estou autenticado como administrador ou gestor clínico (`Role.ADMIN`),
- **Quando** envio uma requisição `PUT /api/v1/telemetria/config-plantao` com novos valores de cota diária (ex: 200), fator $\alpha = 1{,}25$, TMA alvo de 12 minutos e 4 médicos ativos,
- **Então** o sistema valida que os valores atendem os limites operacionais permitidos ($1{,}20 \le \alpha \le 1{,}30$ e médicos $\ge 1$),
- **E** atualiza os parâmetros operacionais da unidade com efeito imediato nas novas admissões,
- **E** renova as informações de capacidade operacional,
- **E** retorna confirmação de atualização (HTTP 200 OK) com os parâmetros consolidados.

### Cenário 2: Rejeição de valores fora dos limites de segurança operacional
- **Dado que** o gestor tenta configurar um fator de segurança $\alpha = 1{,}10$ (abaixo do piso de $1{,}20$) ou quantidade de médicos ativos $= 0$,
- **Quando** submete a alteração,
- **Então** o sistema rejeita a alteração por violação de regra de negócio (HTTP 422 Unprocessable Entity),
- **E** preserva a configuração anterior sem alteração de estado.

---

## 3. Contrato de API

* **Consulta:** `GET /api/v1/telemetria/config-plantao`
* **Atualização:** `PUT /api/v1/telemetria/config-plantao`
* **Headers:** `Authorization: Bearer <jwt_admin>`, `X-Tenant-ID: <org_id>`
* **Payload de Atualização (`ConfigPlantaoUpdate`):**
  ```json
  {
    "cota_diaria_maxima": 250,
    "fator_seguranca_alpha": 1.25,
    "medicos_ativos": 5,
    "tma_alvo_minutos": 12,
    "meta_sla_percentual": 95.0
  }
  ```
* **Resposta Esperada (`200 OK`):** Retorna o registro completo atualizado com timestamp UTC.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo:** Entidade rica `ConfiguracaoPlantao` com validações de invariantes em `src/modules/telemetry/domain/models.py`.
- [x] **Migration Alembic:** Tabela `configuracoes_plantao` criada com RLS multi-tenant (`migrations/versions/0006_telemetry_config_plantao.py`).
- [x] **Apresentação:** Router fino `telemetry_router.py` montado em `/api/v1/telemetria/config-plantao`.
- [x] **Testes Automatizados:**
  - `tests/unit/test_telemetry_model.py`
  - `tests/integration/test_telemetry_router.py`
