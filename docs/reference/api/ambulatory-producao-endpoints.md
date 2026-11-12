# Endpoints de Produção Ambulatorial SUS (BPA-I)

> Contratos de consulta paginada e exportação do arquivo magnético SIA-SUS / BPA-I (RF-08, US-11).

## Contexto

Sob a [ADR-012](../../adrs/ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md), a produção do pronto-atendimento virtual é consolidada para o Sistema Único de Saúde (SUS) vinculada ao ponto de telessaúde CNES 160/006 e ao procedimento SIGTAP `03.01.01.025-0`.

Os endpoints ambulatoriais atendem aos coordenadores de faturamento e gestores dos consórcios intermunicipais (Lei nº 11.107/2005) para auditar os atendimentos fechados no período e extrair o arquivo magnético oficial no layout posicional de colunas fixas do DATASUS (BPA-I).

## Conceito

Todos os endpoints operam sob o prefixo `/api/v1/ambulatory/producao`, exigem o header de tenant `X-Tenant-ID` e token JWT corporativo com papel `ADMIN_GLOBAL`, `GESTOR_UNIDADE` ou `FATURAMENTO`, ou a permissão `Permission.AMBULATORY_CONSOLIDATE`.

### Listagem Paginada da Produção

- **Método / Rota:** `GET /api/v1/ambulatory/producao`
- **Query Params:**
  - `competencia` (string obrigatória, formato `YYYYMM` com mês entre 01 e 12).
  - `page` (int, default `1`, ge=1).
  - `size` (int, default `50`, ge=1, le=100).
- **Status Sucesso:** `200 OK`
- **Envelope de Resposta:** `ListaProducaoAmbulatorialResponse` contendo `items`, `total`, `competencia`, `organizacao_id`, `page` e `size`.

**Exemplo de Resposta (JSON):**
```json
{
  "items": [
    {
      "atendimento_id": "0193132d-2070-7164-8848-fa76f7a63574",
      "cnes": "2000001",
      "codigo_sigtap": "03.01.01.025-0",
      "carater_atendimento": "02",
      "consolidado_em": "2026-11-10T20:15:30Z"
    }
  ],
  "total": 1,
  "competencia": "202611",
  "organizacao_id": 10,
  "page": 1,
  "size": 50
}
```

### Download do Arquivo Magnético BPA-I

- **Método / Rota:** `GET /api/v1/ambulatory/producao/exportar`
- **Query Params:**
  - `competencia` (string obrigatória, formato `YYYYMM`).
- **Status Sucesso:** `200 OK`
- **Headers de Resposta:**
  - `Content-Type: text/plain; charset=ascii`
  - `Content-Disposition: attachment; filename="BPA_I_{competencia}_{cnes}.txt"`
- **Estrutura Posicional:**
  - Linha Header (Tipo 01): 130 caracteres iniciados por `01#BPA#` contendo competência, total de linhas, total de folhas e checksum `cbc-smt-vrf` no domínio `[1111..2221]`.
  - Linhas Detalhe (Tipo 03): 152 caracteres iniciados por `03` contendo CNES, CNS médico, CBO, CNS paciente, SIGTAP `0301010250`, caráter de urgência `02` e dados demográficos em ASCII maiúsculo.

**Amostra Posicional Gerada (ASCII Puro):**
```text
01#BPA#2026110000010000011112UPA DIGITAL CONSORCIO INTERMUNMSYNC 12345678000199SECRETARIA MUNICIPAL DE SAUDE           M03.01     
03200000120261170000000000000122512520261110001010301010250700000000000002M355030R50903500000102             BPASILVA, JOAO                   1991051599
```

### Respostas de Erro (RFC 7807)

| Status | `code` | Cenário |
|---|---|---|
| 400 | `COMPETENCIA_INVALIDA` | Parâmetro `competencia` fora do formato `YYYYMM` ou mês inválido. |
| 401 | `UNAUTHORIZED` | Token ausente, expirado ou inválido. |
| 403 | `FORBIDDEN` | Papel não autorizado (ex.: `PACIENTE` ou médico sem permissão de consolidação). |
| 404 | `PRODUCAO_NAO_ENCONTRADA` | Nenhum registro consolidado no tenant para a competência informada. |

## Onde no código

- Impl: `src/modules/ambulatory/presentation/schemas.py:ListaProducaoAmbulatorialResponse`
- Impl: `src/modules/ambulatory/presentation/dependencies.py:AmbulatoryAuthDep`
- Impl: `src/modules/ambulatory/presentation/routers/producao_router.py:producao_router`
- Impl: `src/modules/ambulatory/presentation/routers/__init__.py:http_router`
- Impl: `src/modules/ambulatory/application/services/producao_service.py:ProducaoAmbulatorialService`
- Impl: `src/modules/ambulatory/domain/bpa_formatter.py:BpaPositionalFormatter`

## Verificação

```bash
uv run pytest tests/unit/test_ambulatory_router.py tests/unit/test_ambulatory_production_service.py -v
uv run pytest tests/architecture/test_routers_are_thin.py tests/architecture/test_main_composition_root.py -v
```

## Ver também

- [Ambulatory Domain](../../explanation/domains/ambulatory-domain.md) — Regras de faturamento e gratuidade SUS
- [US-11: Conclusão de Atendimento e Consolidação Ambulatorial](../../user-stories/US-11-liquidacao-fechamento-contabil.md) — Critérios BDD da história
- [API Error Envelope](./error-envelope.md) — Catálogo unificado de erros RFC 7807
