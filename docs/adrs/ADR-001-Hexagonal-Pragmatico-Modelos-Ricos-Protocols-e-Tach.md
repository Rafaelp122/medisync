# [ADR-001] Adoção de Hexagonal Pragmático com Modelos Ricos, Protocols e Tach

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview de Arquitetura](../03-architecture/overview.md) (RNF-08, RNF-09) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** é uma plataforma de pronto-atendimento virtual aberta. A base de código precisa equilibrar:
1. **Encapsulamento de Regras Clínicas**: Validações de risco, normas do CFM e transições de estado não podem ser dispersas em rotas procedurais (*Anemic Domain Model*).
2. **Produtividade e Manutenibilidade em Python**: Evitar o boilerplate excessivo de converter dados entre camadas conceituais redundantes (*Mapper Hell*).
3. **Desacoplamento de Infraestrutura Externa**: Isolar componentes de alta volatilidade (WebRTC, certificadoras ICP-Brasil, filas em memória e cloud storage).
4. **Isolamento Modular Rigoroso**: Garantir que os módulos verticais (*Bounded Contexts*) permaneçam autônomos e que acoplamentos indevidos sejam barrados antes de chegar à produção.

---

## 2. Drivers de Decisão

* **Eliminação do "Mapper Hell"**: A duplicação de classes puras (`dataclass`/`BaseModel`) e modelos ORM exige conversores manuais bidirecionais (`to_domain`/`to_orm`), aumentando o esforço de manutenção sem ganho de negócio.
* **Aproveitamento Pleno do SQLAlchemy 2.0**: O motor assíncrono do SQLAlchemy possui mais de uma década de otimização em rastreamento de mutações (*dirty tracking*), gerenciamento de sessão assíncrona, *Identity Map* e *Unit of Work*.
* **Subtipagem Estrutural Pythonica**: Uso de `typing.Protocol` (PEP 544) para definir contratos sem exigir herança explícita de `abc.ABC`.
* **Comunicação Inter-Módulos Controlada**: Mecanismo claro para consultas síncronas entre módulos e notificações assíncronas de eventos.
* **Governança de Dependências Automatizada**: Ferramenta rápida e confiável para auditar fronteiras modulares no CI.

---

## 3. Opções Consideradas

### Opção 1: Hexagonal Puro / Clean Architecture Clássica (Entidades 100% Desacopladas do ORM)
* Entidades em Python puro na camada de domínio, e modelos SQLAlchemy isolados na infraestrutura com conversores manuais.
* *Prós*: Independência teórica total do ORM.
* *Contras*: Custo massivo de mapeamento manual (*Mapper Hell*), perda dos recursos nativos do SQLAlchemy (*Identity Map*, *Unit of Work*), erros frequentes de `DetachedInstanceError` e complexidade desproporcional.

### Opção 2: Monólito Tradicional com Modelos Anêmicos (MVC)
* Tabelas de banco contendo apenas colunas, e regras de negócio acumuladas nos roteadores ou em serviços procedurais.
* *Prós*: Rápido para protótipos triviais.
* *Contras*: "Big Ball of Mud", lógica dispersa e duplicada, alta fragilidade a cada nova funcionalidade.

### Opção 3: Hexagonal Pragmático com Modelos Ricos, Protocols e Tach (Adotada)
* **Persistência Relacional**: Os modelos declarativos do SQLAlchemy 2.0 (`Mapped[...]`) são os **Modelos de Domínio Ricos**, encapsulando estado e métodos de negócio. Repositórios encapsulam queries.
* **Portas Externas e Inter-Módulos**: Definidas via `typing.Protocol` para adaptadores voláteis (Valkey, LiveKit, PSC, S3) e chamadas síncronas entre módulos.
* **Event Bus em Memória**: Despacho assíncrono de *Domain Events* para desacoplamento de notificações.
* **Auditoria com Tach**: O **Tach** (em Rust) fiscaliza os limites modulares no `tach.toml`, barrando imports ilegais entre módulos.

---

## 4. Decisão

Adotamos a **Opção 3: Hexagonal Pragmático com Modelos Ricos no SQLAlchemy 2.0, typing.Protocol e Tach**.

### Diretrizes de Execução:
1. **Modelos Ricos**: Transições de estado (ex.: `atendimento.alocar_para_medico()`, `atendimento.registrar_no_show()`) residem no próprio modelo, permitindo testes unitários instantâneos em memória. O domínio pode importar `sqlalchemy.orm` para definir suas entidades ricas.
2. **Identificadores UUIDv7 (RFC 9562)**: Todas as entidades clínicas utilizam `UUIDv7` como chave primária, assegurando ordenação no tempo, inserção contígua no PostgreSQL e desempate determinístico FIFO no Valkey.
3. **Ports via `typing.Protocol` e DTOs**: Aplicadas em `ports.py` para abstrair provedores voláteis e para expor interfaces públicas entre módulos. Consumidores de outros módulos manipulam apenas tipos primitivos ou DTOs imutáveis (`dataclass(frozen=True)`), jamais modelos do SQLAlchemy externos.
4. **Event Bus Assíncrono**: Eventos de domínio desacoplados (ex.: `AtendimentoTriadoEvent`) notificados em memória para listeners concorrentes.
5. **Governança com Tach**: Execução obrigatória de `tach check` em pipelines de CI para validar as fronteiras entre `src/modules/*`.

---

## 5. Consequências

### Positivas:
* **Zero Mapper Hell**: Eliminação de camadas vazias de conversão entre entidades e modelos.
* **Aproveitamento Nativo do ORM**: Preservação do *Unit of Work* e *Identity Map* do SQLAlchemy 2.0.
* **Desacoplamento Real Onde Importa**: Provedores de WebRTC, assinatura digital e storage operam atrás de protocolos estritos.
* **Auditoria Estática Rápida**: Verificação de fronteiras via Tach em milissegundos.

### Riscos Mitigados:
* *Risco de Regras Vazarem para Roteadores*: Mitigado por regras do Tach que proíbem o roteador HTTP de importar repositórios ou executar queries diretamente sem a mediação do serviço.
