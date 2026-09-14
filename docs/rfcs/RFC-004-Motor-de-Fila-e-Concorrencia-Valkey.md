# [RFC-004] Motor de Fila Dinâmica e Concorrência em Valkey

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Versão** | 1.0 |
| **Data** | 2026-09-13 |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RN01, RN02, RN05, RNF-01) |
| **RFC Base** | [RFC-001](RFC-001-Fundacao-Arquitetura-Base-e-Tooling.md) |
| **Decisão de Arquitetura (ADR)** | [ADR-002: Alocação Atômica de Chamadas via Valkey e Lua](../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md) |
| **Componentes Principais** | Valkey 7+, Scripts Lua, Sorted Sets (ZSET), Distributed Atomic Locks |

---

## 1. Contexto & Desafios de Concorrência

Em uma unidade de Pronto-Atendimento Virtual com múltiplos médicos plantonistas operando em regime de alta demanda, ocorrem dois riscos operacionais críticos:
1. **Race Conditions de Alocação (Overbooking)**: Dois ou mais médicos clicarem simultaneamente em *"Chamar Próximo"* e receberem o mesmo paciente, gerando duplicidade de prontuário e sobreposição de salas de teleconsulta (violando a invariante RN02).
2. **Contenção e Gargalo de Banco**: Realizar ordenação contínua de filas via consultas relacionais clássicas com `SELECT ... FOR UPDATE` no PostgreSQL sob concorrência intensa, resultando em lentidão extrema e violação do SLA de resposta $\le 200\text{ ms}$ (RNF-01).

Esta RFC especifica o **motor de fila em memória de alto desempenho**, baseado em Valkey 7+, garantindo ordenação clínica determinística em tempo constante/logarítmico e alocação atômica livre de condições de corrida.

---

## 2. Estrutura de Dados e Indexação da Fila

A fila de atendimento é segregada por tenant utilizando a estrutura **Sorted Set (ZSET)** do Valkey:

- **Namespace da Chave**: `fila:{organizacao_id}:aptos`
- **Membro (Member)**: ID do atendimento (`atendimento_id` convertido para string).
- **Pontuação (Score)**: Valor numérico inteiro de 64 bits calculado deterministicamente para garantir ordenação por prioridade clínica (níveis 1 a 5, onde menor valor numérico representa maior gravidade) desempadada estritamente por ordem cronológica de entrada (FIFO - RN01):

$$\text{Score} = (\text{prioridade\_clinica} \times 10^{12}) + \text{timestamp\_entrada\_epoch}$$

*Exemplo*:
- Paciente Nível 2 (Muito Urgente) que ingressou em `1726250000`:  
  $\text{Score} = (2 \times 10^{12}) + 1726250000 = 2001726250000$
- Paciente Nível 4 (Pouco Urgente) que ingressou 10 minutos antes (`1726249400`):  
  $\text{Score} = (4 \times 10^{12}) + 1726249400 = 4001726249400$

Como o Valkey ordena ZSETs em ordem crescente, a busca pelo próximo paciente mais urgente é uma operação de complexidade $\mathcal{O}(\log N)$:
```redis
ZRANGE fila:{organizacao_id}:aptos 0 0
```

---

## 3. Alocação Atômica Médico-Paciente via Script Lua (RN02)

Para garantir que a verificação de disponibilidade, a trava do médico, a trava do paciente e a remoção da fila ocorram em uma única etapa indivisível, adota-se um script Lua executado no Valkey via comando `EVALSHA`.

### 3.1 Script de Alocação (`src/modules/fila/lua/alocar_chamada.lua`)

```lua
-- KEYS[1]: lock:{org_id}:medico:{medico_id}
-- KEYS[2]: lock:{org_id}:atendimento:{atendimento_id}
-- KEYS[3]: fila:{org_id}:aptos
-- ARGV[1]: medico_id
-- ARGV[2]: atendimento_id
-- ARGV[3]: ttl_segundos (padrão: 45)

-- 1. Verifica se o médico ou o atendimento já possuem locks ativos
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[2]) == 1 then
    return 0 -- Conflito: médico ou atendimento já ocupados
end

-- 2. Confirma se o atendimento ainda está de fato presente na fila de aptos
local rank = redis.call('ZRANK', KEYS[3], ARGV[2])
if not rank then
    return -1 -- Atendimento não disponível mais na fila (já capturado por outro nó)
end

-- 3. Remove atomicamente da fila e aplica ambos os locks vinculados com TTL
redis.call('ZREM', KEYS[3], ARGV[2])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[3])

return 1 -- Alocação atômica confirmada com sucesso
```

### 3.2 Interpretação dos Códigos de Retorno & Loop de Retentativa
- **`1` (Sucesso)**: O paciente foi reservado exclusivamente para o médico chamador, removido da fila pública e os locks de 45 segundos foram ativados.
- **`0` (Conflito de Lock)**: O médico já possui uma chamada em andamento ou o atendimento está em transição. A API rejeita a requisição com código HTTP 409 (Conflict).
- **`-1` (Item Esgotado / Concorrência Concorrente)**: O atendimento acabou de ser capturado por outro médico concorrente. O serviço de aplicação implementa um **loop de retentativa em memória com até 3 iterações**:
  1. O backend busca o próximo elemento no ZSET (`ZRANGE offset offset`).
  2. Executa novamente o script Lua com o novo candidato.
  3. Se as 3 tentativas falharem por concorrência simultânea extrema ou a fila se esvaziar, o endpoint retorna HTTP 204 (No Content), sinalizando ausência temporária de pacientes aptos sem gerar erro ao médico.

---

## 4. Controle de Admissão e Backpressure Estocástico (RN05)

Para proteger a equipe médica contra estafa (*burnout*) e mitigar a formação de filas com tempos de espera infinitos no encerramento do turno, a admissão na fila virtual aplica um filtro de saturação matemático antes de acolher novos pacientes.

### 4.1 Condições de Bloqueio da Admissão
O ingresso de novos atendimentos é suspenso preventivamente se qualquer uma das condições for satisfeita:

1. **Ausência de Médicos Ativos (Guarda de Divisão por Zero)**:
   Se $\text{Médicos Ativos} \le 0$, a admissão é suspensa imediatamente (`QUEUE_PAUSED_NO_DOCTORS`), prevenindo divisão por zero e represamento de pacientes sem equipe assistencial conectada.

2. **Cota Diária Total**:
   $$\text{Total de Admissões Concluídas no Dia} \ge \text{Cota Diária Máxima}$$

3. **Equilíbrio Capacidade vs. Demanda Restante**:
   $$\frac{\text{Pacientes Aguardando} \times \text{TMA Estimado} \times \alpha}{\text{Médicos Ativos no Turno}} > \text{Tempo Restante de Plantão}$$

Onde:
- **$\alpha$ (Fator de Margem de Segurança)**: Coeficiente estocástico configurável por tenant ($1{,}20 \le \alpha \le 1{,}30$, padrão: $1{,}25$), que absorve variabilidade clínica e imprevistos de conexão.
- **TMA Estimado**: Tempo Médio de Atendimento histórico da unidade (em segundos).
- **Médicos Ativos**: Contagem em tempo real de profissionais logados e disponíveis no plantão.
- **Parametrização 24/7**: Em pronto-atendimentos com operação contínua 24/7 (escalas rotativas perpétuas), o *Tempo Restante de Plantão* é calculado com base na janela do turno corrente (ex.: blocos de 12 horas: 07h-19h / 19h-07h) ou pelo teto do SLA Máximo Tolerável da Unidade.

### 4.2 Notificação de Transbordo
Quando a admissão é bloqueada, a API retorna mensagem humanizada de saturação temporária e emite o evento assíncrono `QUEUE_OVERFLOW_TRANSIT` para integração com centrais de regulação ou SMS/WhatsApp informando unidades físicas de apoio.

---

## 5. Resiliência e Auto-Cura do Valkey

Embora o Valkey atue em memória para garantir respostas em $\le 200\text{ ms}$, o estado persistente do sistema reside de forma definitiva no PostgreSQL. Para garantir tolerância a desastres e reinicializações de contêineres:

1. **Persistência AOF Ativa**: O servidor Valkey opera com `--appendonly yes --appendfsync everysec`, garantindo que no máximo 1 segundo de dados em trânsito possa ser perdido em falha abrupta de energia.
2. **Reconciliação Automática no Startup**: Durante o ciclo de inicialização (*lifespan*) da aplicação FastAPI, uma rotina varre o banco relacional e repopula os Sorted Sets com todos os registros em estado `APTO_PARA_CHAMADA`:

```python
async def reconciliar_filas_em_memoria(session_factory, valkey):
    """Reconstrói os Sorted Sets do Valkey após reinicializações."""
    async with session_factory() as session:
        stmt = select(AtendimentoModel).where(
            AtendimentoModel.status == StatusAtendimento.APTO_PARA_CHAMADA
        )
        result = await session.execute(stmt, execution_options={"ignorar_tenant": True})
        atendimentos = result.scalars().all()
        for at in atendimentos:
            timestamp = int(at.chamada_iniciada_em.timestamp()) if at.chamada_iniciada_em else 0
            score = (at.prioridade_clinica * 10**12) + timestamp
            await valkey.zadd(f"fila:{at.organizacao_id}:aptos", {str(at.id): score}, nx=True)
```

3. **Prevenção de Inconsistência Transacional Lua $\leftrightarrow$ PostgreSQL (Dual-Write Hazard)**:
Se a API sofrer um crash imediatamente após o script Lua remover o paciente da fila mas antes de completar o commit transacional no PostgreSQL ou enfileirar o job de ring timeout no ARQ:
- O lock do médico no Valkey expirará em 45 segundos por TTL.
- No entanto, o paciente ficaria órfão (fora do ZSET do Valkey e no banco com status `APTO_PARA_CHAMADA`).
- **Mitigação com Auto-Cura (Sweeper a cada 60s)**: Conforme especificado na [RFC-005](RFC-005-Processamento-Assincrono-e-Ring-Timeout.md), um worker periódico no ARQ busca atendimentos em `APTO_PARA_CHAMADA` com mais de 60 segundos sem atualização que não estejam presentes no ZSET do Valkey nem possuam locks de atendimento ativos, reinjetando-os no ZSET com sua prioridade e timestamp originais preservados.

---

## 6. Decisões Arquiteturais Relacionadas (ADRs)

A fundamentação da escolha de estruturas ZSET em memória com scripts Lua (em detrimento de travas transacionais relacionais no PostgreSQL ou locks em processo Python), assim como os trade-offs de desempenho e mitigação de falhas, estão documentados em:
- **[ADR-002: Alocação Atômica de Chamadas via Valkey Sorted Sets e Scripts Lua](../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md)**
- **[ADR-006: Resolução de No-Show com Ring Timeout Determinístico via Jobs Diferidos no ARQ](../adrs/ADR-006-Ring-Timeout-Deterministico-via-Jobs-Diferidos.md)**
