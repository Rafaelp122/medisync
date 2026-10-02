-- Script de Alocação Atômica Médico-Paciente (ADR-002)
-- KEYS[1]: lock:{org_id}:medico:{medico_id}
-- KEYS[2]: lock:{org_id}:atendimento:{atendimento_id}
-- KEYS[3]: fila:{org_id}:aptos
-- ARGV[1]: medico_id
-- ARGV[2]: atendimento_id
-- ARGV[3]: ttl_segundos (padrão: 45)

-- 1. Verifica se o médico chamador já possui lock ativo (bloqueio do profissional)
if redis.call('EXISTS', KEYS[1]) == 1 then
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
