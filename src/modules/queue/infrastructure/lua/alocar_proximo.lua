-- Script de Seleção e Alocação Atômica Multi-Candidato na Fila (ADR-002)
-- KEYS[1]: lock:medico:{medico_id}
-- KEYS[2]: lock:atendimento: (prefixo para cada candidato)
-- KEYS[3]: fila:aptos
-- KEYS[4]: lock:consulta_ativa:medico:{medico_id}
-- ARGV[1]: medico_id
-- ARGV[2]: ttl_segundos (padrão: 45)
-- ARGV[3]: max_scan (padrão: 50)

-- 1. Verifica se o médico possui ring ativo ou consulta em andamento
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[4]) == 1 then
    return {0, ''}
end

-- 2. Varre janela de candidatos elegíveis no ZSET em um único round-trip atômico
local max_scan = tonumber(ARGV[3]) or 50
if max_scan < 1 then
    max_scan = 1
end

local candidatos = redis.call('ZRANGE', KEYS[3], 0, max_scan - 1)
for _, cand in ipairs(candidatos) do
    local lock_atendimento_key = KEYS[2] .. cand
    if redis.call('EXISTS', lock_atendimento_key) == 0 then
        redis.call('ZREM', KEYS[3], cand)
        redis.call('SET', KEYS[1], cand, 'EX', ARGV[2])
        redis.call('SET', lock_atendimento_key, ARGV[1], 'EX', ARGV[2])
        return {1, cand}
    end
end

return {-1, ''}
