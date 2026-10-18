# MediSync Express — Documentação Canônica

> **Missão do PA Digital 24/7:** Plataforma aberta de telemedicina emergencial de alta disponibilidade, projetada para acolhimento ágil (< 45s), triagem estruturada por gravidade, ordenação atômica em fila virtual (Valkey + Lua), prontuário SOAP em conformidade CFM e teleconsulta WebRTC segura.

---

## 1. Mapa dos 4 Quadrantes Diátaxis

A documentação do MediSync é estruturada segundo a metodologia Diátaxis, separando aprendizado prático, resolução de problemas, referência técnica e entendimento conceitual:

- **[Tutorials](tutorials/index.md)**: Guias orientados a aprendizado passo a passo para novos desenvolvedores, cobrindo desde a subida inicial do ambiente ([Onboarding Quickstart](tutorials/onboarding-quickstart.md)) até a construção da primeira fatia vertical ([Backend First Feature](tutorials/backend-first-feature.md)).
- **[How-to](how-to/index.md)**: Receitas práticas para tarefas rotineiras e resolução de problemas, incluindo [Setup Local](how-to/dev-environment/setup-local.md), criação de endpoints ([Create Module Endpoint](how-to/backend/create-module-endpoint.md)) e execução da suíte de testes ([Run Tests](how-to/backend/run-tests.md)).
- **[Reference](reference/index.md)**: Especificações técnicas normativas e contratos estritos, detalhando [API Error Envelope](reference/api/error-envelope.md), [Environment Variables](reference/environment/variables.md), pipeline de CI/CD e padrões de testes.
- **[Explanation](explanation/index.md)**: Discussões conceituais de arquitetura, trade-offs e invariantes clínicas ([Architecture Overview](explanation/architecture/overview.md), [Concurrency & Queues](explanation/architecture/concurrency-and-queues.md) e [Concepts](explanation/concepts/index.md)).

---

## 2. Decisões de Arquitetura (ADRs)

O registro formal das decisões arquiteturais adotadas no projeto está catalogado em [ADRs](adrs/README.md):

- [ADR-001](adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md) — Hexagonal Pragmático, Modelos Ricos, Protocols e Tach
- [ADR-002](adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md) — Alocação Atômica em Fila com Valkey e Script Lua
- [ADR-003](adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md) — Multi-Tenancy Lógico com PostgreSQL Row-Level Security (RLS)
- [ADR-004](adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md) — Worker Assíncrono ARQ sobre Valkey
- [ADR-005](adrs/ADR-005-Desacoplamento-de-Midia-LiveKit-SFU.md) — Desacoplamento de Mídia com LiveKit SFU
- [ADR-006](adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md) — Assinatura Digital ICP-Brasil em Nuvem (PSC)
- [ADR-007](adrs/ADR-007-Auditoria-Imutavel-Append-Only.md) — Trilha de Auditoria Imutável Append-Only
- [ADR-008](adrs/ADR-008-Padronizacao-de-DTOs-e-Eliminacao-de-Mapper-Hell-na-Apresentacao.md) — Padronização de DTOs e Eliminação de Mapper Hell
- [ADR-009](adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md) — Configurações Polimórficas e Desacoplamento nos Composition Roots
- [ADR-010](adrs/ADR-010-Estrategia-DevSecOps-Defesa-em-Profundidade-de-Segredos-e-SAST.md) — Estratégia DevSecOps e Prevenção de Vazamento de Segredos

---

## 3. Living Specifications (User Stories US-01 a US-13)

Especificações comportamentais em Gherkin com checklist de código vivo, consolidadas no [Catálogo de User Stories](user-stories/README.md):

- [US-01](user-stories/US-01-acolhimento-triagem-tcle.md): Acolhimento, Triagem Estruturada e TCLE Digital (Fase 1)
- [US-02](user-stories/US-02-autenticacao-passwordless-otp.md): Reconexão e Autenticação Passwordless OTP
- [US-03](user-stories/US-03-elegibilidade-onboarding-fase2.md): Validação de Elegibilidade e Enriquecimento CFM (Fase 2)
- [US-04](user-stories/US-04-controle-admissao-backpressure.md): Backpressure e Controle Dinâmico de Admissão
- [US-05](user-stories/US-05-regularizacao-elegibilidade-fila.md): Tratamento de Exceções e Regularização de Fila
- [US-06](user-stories/US-06-deterioracao-clinica-escape-samu.md): Monitoramento de Sintomas e Escape SAMU 192
- [US-07](user-stories/US-07-alocacao-chamada-medica.md): Alocação Atômica de Chamada Médica
- [US-08](user-stories/US-08-atendimento-chamada-no-show.md): Atendimento da Chamada e Gestão de No-Show
- [US-09](user-stories/US-09-teleconsulta-pep-soap.md): Teleconsulta Síncrona e Registro PEP SOAP
- [US-10](user-stories/US-10-prescricao-assinatura-icp-brasil.md): Prescrição Eletrônica e Assinatura ICP-Brasil
- [US-11](user-stories/US-11-liquidacao-fechamento-contabil.md): Conclusão de Consulta e Liquidação Contábil
- [US-12](user-stories/US-12-parametrizacao-politicas-plantao.md): Parametrização e Políticas Operacionais do Plantão
- [US-13](user-stories/US-13-telemetria-painel-operacional.md): Telemetria Operacional e Painel do Plantão (CQRS)

---

## 4. Comandos Rápidos de Bootstrap e Verificação

Para inicializar a infraestrutura local, instalar dependências e validar a integridade completa do projeto:

```bash
just up        # Sobe PostgreSQL e Valkey no Docker
just install   # Sincroniza o ambiente virtual com uv
just check     # Roda fmt, lint, typecheck, tach e testes
```
