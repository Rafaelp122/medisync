# [ADR-009] Configurações Polimórficas por Perfil e Desacoplamento nos Composition Roots

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-10-15 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md), [ADR-008](ADR-008-Padronizacao-de-DTOs-e-Eliminacao-de-Mapper-Hell-na-Apresentacao.md), [Composition Root](../explanation/concepts/composition-root-and-dependencies.md) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** adota o Hexagonal Pragmático com Composition Roots modulares (`src/modules/*/composition.py`) conforme a [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md).

No entanto, o gerenciamento de configurações e injeção de dependências apresentava fragilidades arquiteturais:

1. **Configuração Monolítica com Defaults Inseguros**: A classe `Settings` em `src/core/config.py` reunia todos os ambientes em uma estrutura plana única. Segredos de desenvolvimento (`SECRET_KEY="dev-insecure-..."`, `LIVEKIT_API_KEY="devkey"`) e flags de debug podiam subir acidentalmente para produção sem travas de validação automática.
2. **Singletons Globais Mutáveis nos Módulos**: Módulos como `triage` mantinham referências globais mutáveis (`_emergency_notifier: EmergencyNotifierPort | None = None` com `global _emergency_notifier`). Esse padrão introduzia acoplamento temporal, vazamento de estado (*state leakage*) entre execuções de teste e impedia paralelismo determinístico com `pytest-xdist`.
3. **Acoplamento Direto de Serviços com Configurações**: Serviços de aplicação (`application/services/`) importavam e chamavam `get_settings()` diretamente no meio da lógica de negócios, violando o princípio de inversão de dependências e dificultando testes unitários sem *monkeypatching* global.
4. **Acoplamento Forçado com Serviços Externos nos Testes Rápidos**: Testes unitários que navegavam por rotas dependiam de instâncias ativas do Valkey ou adaptadores concretos de rede para rate limiters e revogação de tokens, retardando o ciclo de feedback da equipe.

---

## 2. Drivers de Decisão

* **Segurança Fail-Fast em Produção**: Garantir em tempo de inicialização (startup) que credenciais fracas, URLs de teste e modos de depuração não sejam aceitos em ambiente produtivo.
* **Isolamento e Concorrência Segura de Testes**: Eliminar qualquer estado global mutável em nível de módulo para viabilizar execução paralela veloz e determinística (`just test-fast`).
* **Testabilidade e Execução Sem Docker**: Permitir a alternância declarativa de adaptadores de infraestrutura para implementações em memória (`in_memory`) sem modificar o código de produção.
* **Hexagonal Pragmático Rigoroso**: Centralizar a resolução de dependências técnicas e leitura de ambiente exclusivamente na camada de composição (`composition.py`), mantendo os serviços de aplicação 100% puros e agnósticos ao runtime.

---

## 3. Opções Consideradas

### Opção 1: Configuração Monolítica com Checagens Manuais nos Routers
* Manter um único objeto `Settings` e adicionar verificações manuais de segurança e condicionais dentro de cada roteador ou serviço.
* *Contras*: Proliferação de condicionais espalhadas, alto risco de esquecimento e violação do princípio de responsabilidade única.

### Opção 2: Abordagem Estilo Django Multi-Settings com Módulos Separados
* Criar arquivos separados (`settings_prod.py`, `settings_dev.py`, `settings_test.py`) selecionados via variável de ambiente `DJANGO_SETTINGS_MODULE`.
* *Contras*: No ecossistema moderno FastAPI + Pydantic v2, divide os schemas de validação, duplica código e perde a validação estrita de tipos do `basedpyright` e tipagem unificada.

### Opção 3: Hierarquia Polimórfica com Pydantic Settings e Fiação Dinâmica (Adotada)
* Herança orientada a perfil a partir de `CommonSettings`: `DevelopmentSettings`, `TestSettings` e `ProductionSettings`.
* Resolução em tempo de carregamento via discriminador `ENVIRONMENT`.
* Seletores de backend declarativos (`RATE_LIMIT_BACKEND`, `TOKEN_REVOCATION_BACKEND`, etc.).
* Fiação dinâmica nos Composition Roots sem singletons globais mutáveis.

---

## 4. Decisão

Adotamos a **Opção 3: Hierarquia Polimórfica com Pydantic Settings e Fiação Dinâmica**.

### Diretrizes Mandatórias de Implementação:

1. **Perfis Polimórficos e Fail-Fast (`src/core/config.py`)**:
   - `CommonSettings`: Contém a definição canônica de todos os campos com valores seguros de desenvolvimento.
   - `DevelopmentSettings`: Ativa `DEBUG=True` e defaults amigáveis para Docker Compose local.
   - `TestSettings`: Define `ENVIRONMENT="test"`, `DEBUG=False` e configura seletores para `in_memory`.
   - `ProductionSettings`: Desativa `DEBUG=False` e impõe `@model_validator(mode="after")` que aborta imediatamente a execução se encontrar senhas padrão de teste, segredos fracos ou webhooks inseguros.
   - `get_settings()` instancia e armazena em cache (`@lru_cache`) a classe especializada correspondente ao valor de `ENVIRONMENT`.

2. **Fiação Dinâmica nos Composition Roots (`src/modules/*/composition.py`)**:
   - Proíbe-se o uso da instrução `global` e de variáveis mutáveis de módulo (`_adapter: Port | None = None`).
   - Adaptadores concretos são selecionados dinamicamente via `get_settings()` ou parâmetros de configuração injetados.
   - Todo Composition Root expõe o par canônico de fábricas:
     * `get_*_service(...)`: Injetor assíncrono para o ecossistema FastAPI via `Depends()`.
     * `build_*_service_for_session(session: AsyncSession, ...)`: Fábrica pura para workers assíncronos (ARQ), CLI e suítes de teste.

3. **Inversão de Dependências nos Serviços (`application/services/`)**:
   - É **terminantemente proibido** importar `get_settings()` ou `src.core.config` dentro de qualquer arquivo em `src/modules/*/application/services/`.
   - Serviços devem receber seus parâmetros e credenciais primitivas (`secret_key`, `access_token_expire_minutes`, `is_debug`, etc.) exclusivamente via construtor `__init__`, preenchidos pela camada de composição.

4. **Guardas Automatizados de Arquitetura**:
   - O teste AST `tests/architecture/test_services_and_composition.py` é executado em `just check` para barrar automaticamente qualquer violação dessas diretrizes.

---

## 5. Consequências

### Positivas:
* **Segurança Ativa em Produção**: Erros de configuração de infraestrutura são barrados antes do tráfego clínico ser aceito.
* **Testes Determinísticos e Ultrarrápidos**: Suítes unitárias executam em memória em milissegundos sem depender de Valkey ou contêineres Docker (`just test-fast`).
* **Concorrência Perfeita**: Zero risco de poluição entre testes em execuções paralelas multi-thread ou multi-core.
* **Alta Manutenibilidade**: Trocar uma implementação de mensageria ou rate limit exige alterar apenas o adaptador e o seletor correspondente, sem tocar nas regras de negócio.

### Riscos Mitigados:
* *Risco de Incompatibilidade Retroativa*: Mitigado pelo alias `Settings = CommonSettings`, assegurando que importações legadas continuem funcionando sem quebra de contrato.
