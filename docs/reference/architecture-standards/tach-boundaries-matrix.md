# Matriz de Fronteiras Modulares Tach

> Matriz canônica de camadas hexagonais, limites modulares e dependências permitidas via Tach no MediSync Express.

## Contexto

O MediSync Express adota a arquitetura Hexagonal Pragmática (ADR-001) para conciliar desacoplamento modular, tipagem estrita e alta performance de execução.
Para impedir a erosão arquitetural e o acoplamento desordenado entre domínios clínicos, o repositório emprega o `tach` (`tach.toml`) como linter arquitetural estrito no pipeline de integração contínua (`just tach`).
A governança estabelece isolamento físico e lógico entre os módulos de negócio (`auth`, `identity`, `triage`, `queue`, `consultation`, `billing`, `telemetry`), a base compartilhada (`core`) e o executor assíncrono (`worker`).
Qualquer violação das regras de dependência ou importação direta não autorizada entre camadas ou módulos causa falha imediata na checagem estática.
A barreira estrutural garante que regras de transação (um commit por caso de uso no service) e o padrão de routers finos sejam rigorosamente respeitados.

## Conceito

A separação modular segue o princípio *Inside-Out* estrito (Stage B), onde camadas internas nunca conhecem camadas externas, e módulos de negócio não acessam diretamente detalhes de persistência ou regras internas de outros módulos.

### Regras Universais por Camada

| Camada | Propósito Arquitetural | Dependências Permitidas | Proibições Estritas |
|---|---|---|---|
| `domain` | Modelos ricos, validações clínicas e regras de negócio invariantes. | `src.core` | Proibido importar `application`, `infrastructure`, `presentation` ou outros módulos. |
| `application` | Casos de uso, orquestração e contratos de portas (`typing.Protocol`). | `src.core`, `domain` local | Proibido importar `infrastructure`, `presentation` ou frameworks web/ORM. |
| `infrastructure` | Adaptadores técnicos de banco de dados, storage S3, criptografia e mensageria. | `src.core`, `domain` local, `application` local | Proibido importar `presentation` ou ser importado por outros módulos. |
| `composition` | Composition Root do módulo: instanciação e injeção de dependências. | `src.core`, `domain`, `application`, `infrastructure` locais; `application` e `composition` externos autorizados | Proibido importar `presentation` ou conter variáveis globais mutáveis. |
| `presentation` | Routers HTTP/WS FastAPI, schemas Pydantic e dependências de rota. | `src.core`, `application` local, `composition` local | Proibido importar `infrastructure`, `sqlalchemy` ou instanciar services diretamente. |

### Matriz Completa de Módulos e Dependências (`tach.toml`)

| Pacote / Camada | Dependências Permitidas (`depends_on`) | Comunicação Externa Permitida |
|---|---|---|
| `src.core` | `[]` | Nenhuma (camada fundacional transversal compartilhada). |
| `src.modules.auth.domain` | `src.core` | Isolado. Regras de credenciais e hashing. |
| `src.modules.auth.application` | `src.core`, `auth.domain` | Isolado. Casos de uso de login, tokens e OTP. |
| `src.modules.auth.infrastructure` | `src.core`, `auth.application`, `auth.domain` | Adaptador Valkey de revogação de tokens JWT. |
| `src.modules.auth.composition` | `src.core`, `auth.*`, `identity.application`, `identity.composition` | Consome serviços de `identity` via composition. |
| `src.modules.auth.presentation` | `src.core`, `auth.application`, `auth.composition` | Routers finos e schemas de autenticação. |
| `src.modules.billing.domain` | `src.core` | Isolado. Enums e regras de elegibilidade de convênio. |
| `src.modules.billing.application` | `src.core`, `billing.domain` | Define portas de elegibilidade e notificação de recusa. |
| `src.modules.billing.infrastructure` | `src.core`, `billing.application`, `billing.domain` | Adaptadores de gateway privado e SUS isento. |
| `src.modules.billing.composition` | `src.core`, `billing.application`, `billing.domain`, `billing.infrastructure` | Fornece `ElegibilidadeService` para worker e API. |
| `src.modules.consultation.domain` | `src.core` | Isolado. Modelos de prontuário, documentos e prescrições. |
| `src.modules.consultation.application` | `src.core`, `consultation.domain` | Define portas de storage, PDF, assinatura e LiveKit. |
| `src.modules.consultation.infrastructure` | `src.core`, `consultation.application`, `consultation.domain` | Adaptadores PyHanko, S3 MinIO e ReportLab. |
| `src.modules.consultation.composition` | `src.core`, `consultation.*`, `identity.app/comp`, `queue.app/comp` | Consome dados de profissional/paciente e fila. |
| `src.modules.consultation.presentation` | `src.core`, `consultation.application`, `consultation.composition` | Routers finos de PEP, documentos e teleconsulta. |
| `src.modules.identity.domain` | `src.core` | Isolado. Modelos de organizações, profissionais e pacientes. |
| `src.modules.identity.application` | `src.core`, `identity.domain` | Define portas de busca de pacientes e profissionais. |
| `src.modules.identity.infrastructure` | `src.core`, `identity.application`, `identity.domain` | Repositórios SQLAlchemy e adaptadores SMS. |
| `src.modules.identity.composition` | `src.core`, `identity.application`, `identity.domain`, `identity.infrastructure` | Expõe `IdentityReaderPort` para outros módulos. |
| `src.modules.identity.presentation` | `src.core`, `identity.application`, `identity.composition` | Routers de onboarding e pacientes. |
| `src.modules.queue.domain` | `src.core` | Isolado. Máquina de estados de atendimentos na fila. |
| `src.modules.queue.application` | `src.core`, `queue.domain` | Define portas de alocação de chamadas e triagem. |
| `src.modules.queue.infrastructure` | `src.core`, `queue.application`, `queue.domain` | Scripts Lua atômicos no Valkey e repositórios de fila. |
| `src.modules.queue.composition` | `src.core`, `queue.*`, `triage.application`, `triage.composition` | Integra classificação de risco da triagem. |
| `src.modules.queue.presentation` | `src.core`, `queue.application`, `queue.composition` | Routers de admissão, chamada e cancelamento. |
| `src.modules.triage.domain` | `src.core` | Isolado. Modelos de classificação Manchester e sinais vitais. |
| `src.modules.triage.application` | `src.core`, `triage.domain` | Orquestra protocolo Manchester e cálculo de score. |
| `src.modules.triage.infrastructure` | `src.core`, `triage.application`, `triage.domain` | Persistência de respostas e avaliações de triagem. |
| `src.modules.triage.composition` | `src.core`, `triage.application`, `triage.domain`, `triage.infrastructure` | Expõe serviço de triagem para a fila. |
| `src.modules.telemetry.domain` | `src.core` | Isolado. Modelos de telemetria, painel e plantão. |
| `src.modules.telemetry.application` | `src.core`, `telemetry.domain` | Define portas de métricas operacionais e plantão. |
| `src.modules.telemetry.infrastructure` | `src.core`, `telemetry.application`, `telemetry.domain` | Agregações Valkey e repositórios analíticos. |
| `src.modules.telemetry.composition` | `src.core`, `telemetry.application`, `telemetry.domain`, `telemetry.infrastructure` | Fornece dependências do painel e plantão. |
| `src.modules.telemetry.presentation` | `src.core`, `telemetry.application`, `telemetry.composition` | Routers de métricas e painel em tempo real. |
| `src.worker` | `src.core`, `queue.*`, `billing.*`, `identity.*` | Executa jobs em background (timeout de ring, elegibilidade). |

### Proibição de Imports Cross-Module Diretos

1. **Vedação de Modelos e Tabelas:** Um módulo jamais importa `src.modules.<outro>.domain.models` nem `infrastructure`. O acesso a dados de outros domínios é realizado exclusivamente por portas abstratas (`typing.Protocol`) e DTOs imutáveis (`@dataclass(frozen=True)` ou Pydantic v2).
2. **Resolução Exclusiva no Composition Root:** As portas declaradas na camada `application` de um módulo só podem ser satisfeitas por adaptadores instanciados no arquivo `composition.py`.
3. **Routers Finos:** Routers em `presentation/routers/` interagem estritamente com schemas Pydantic de entrada/saída e dependências injetadas de `composition.py`. São terminantemente proibidas chamadas diretas a `session.commit()`, queries SQLAlchemy ou instâncias diretas de serviços.
4. **Aciclicidade Obrigatória:** A configuração `forbid_circular_dependencies = true` do `tach.toml` impede qualquer relação de dependência cíclica entre módulos e camadas.

## Onde no código

- Impl: `tach.toml`
- Spec: `docs/adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md`
- Spec: `docs/adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md`
- Prova viva: `tests/architecture/test_routers_are_thin.py:test_routers_do_not_import_forbidden_layers`
- Prova viva: `tests/architecture/test_services_and_composition.py:test_composition_roots_do_not_import_presentation`
- Prova viva: `tests/architecture/test_main_composition_root.py:test_main_does_not_import_infrastructure`
- Ver: `just tach`
- Ver: `rg -n "depends_on" tach.toml`

## Verificação

```bash
just tach
uv run tach check
uv run pytest tests/architecture/ -v
```

Saída esperada: `✅ All modules validated!` e todos os testes de arquitetura aprovados sem violações.

## Ver também

- [ADR-001 Hexagonal Pragmático](../../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)
- [ADR-009 Desacoplamento nos Composition Roots](../../adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md)
- [Documentation standards](documentation-standards.md)
- [Hexagonal pragmático](../../explanation/concepts/hexagonal-pragmatico.md)
- [Inter-module protocols](../../explanation/concepts/inter-module-protocols.md)
- [Composition root and dependencies](../../explanation/concepts/composition-root-and-dependencies.md)
- [Test doubles catalog](../testing/test-doubles-catalog.md)
