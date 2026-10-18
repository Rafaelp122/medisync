# Domains

Visão conceitual por domínio clínico — regras, invariantes e vocabulário ubíquo de cada módulo.

## Densos

- [identity-domain.md](./identity-domain.md) — cadastro em 2 fases (CFM 1.821), dependentes pediátricos e profissionais.
- [triage-domain.md](./triage-domain.md) — classificação de risco e salvaguarda SAMU.
- [queue-domain.md](./queue-domain.md) — ordenação, alocação atômica e backpressure.
- [consultation-domain.md](./consultation-domain.md) — ato médico, evolução e PEP.
- [billing-domain.md](./billing-domain.md) — elegibilidade de convênio e faturamento.
- [telemetry-domain.md](./telemetry-domain.md) — governança de plantão, parametrização estocástica e painel CQRS.

## Transversais

- [auth-domain.md](./auth-domain.md) — autenticação OWASP/Argon2id, lockout, OTP SMS passwordless e revogação no Valkey.
- [context-map.md](./context-map.md) — ports abstratas e direção das dependências.
- [domain-events.md](./domain-events.md) — eventos ponto a ponto sem barramento.
