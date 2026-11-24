-- Script de Alocação Atômica Médico-Paciente 4-Keys (ADR-002 / ADR-013)
-- KEYS[1]: lock:medico:{medico_id}
-- KEYS[2]: lock:atendimento:{atendimento_id}
-- KEYS[3]: fila:aptos
-- KEYS[4]: lock:consulta_ativa:medico:{medico_id}
-- ARGV[1]: medico_id
-- ARGV[2]: atendimento_id
-- ARGV[3]: ttl_segundos (padrão: 45)

-- 1. Verifica se o médico chamador possui lock de ring ou consulta ativa (HTTP 409)
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[4]) == 1 then
    return 0 -- Conflito: médico já ocupado com chamada ou consulta em andamento (HTTP 409)
end

-- 2. Verifica se o atendimento pretendido já foi capturado por outro médico
if redis.call('EXISTS', KEYS[2]) == 1 then
    return -1 -- Atendimento já reservado simultaneamente (aciona retry na aplicação)
end

-- 3. Confirma se o atendimento ainda está de fato presente na fila de aptos
local rank = redis.call('ZRANK', KEYS[3], ARGV[2])
if not rank then
    return -1 -- Atendimento não disponível mais na fila (aciona retry na aplicação)
end

-- 4. Remove atomicamente da fila e aplica ambos os locks vinculados com TTL de ring
redis.call('ZREM', KEYS[3], ARGV[2])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[3])

return 1 -- Alocação atômica confirmada com sucesso
