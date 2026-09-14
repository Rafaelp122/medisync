# [ADR-001] Adoção de Monólito Modular Pragmático com Modelos Ricos

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RNF-08, RNF-09) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** é uma plataforma open source para Pronto-Atendimento Virtual em unidades de saúde públicas (SUS) e operadoras privadas. A aplicação precisa rodar com eficiência tanto em pequenos municípios com infraestrutura modesta de hardware (1 a 2 vCPUs) quanto em operações de grande escala.

Precisamos definir o estilo arquitetural do backend para equilibrar:
1. Baixa complexidade operacional e facilidade de deploy em contêiner único (RNF-08).
2. Alta velocidade de desenvolvimento e sustentabilidade de código sem camadas e conversões redundantes.
3. Encapsulamento rigoroso de regras clínicas e invariantes no modelo de domínio, combatendo modelos anêmicos.
4. Isolamento defensivo concentrado exclusivamente nas bordas onde a volatilidade externa real acontece (mídia WebRTC, assinadores ICP-Brasil, mensageria e object storage).

---

## 2. Drivers de Decisão

- **Eliminação do "Mapper Hell"**: Evitar a sobrecarga de duplicar estruturas de dados em classes puras separadas dos modelos ORM, o que exigiria conversores manuais (`to_entity`/`to_model`) em todos os repositórios.
- **Modelos Ricos contra Anemia de Negócio**: Invariantes clínicas, validações regulatórias (CFM, Portaria 344/98) e transições de estado devem residir diretamente nas entidades/modelos, e não espalhadas em scripts procedurais.
- **Aproveitamento Pleno da Stack Consolidada**: O FastAPI, o SQLAlchemy 2.0 e o Alembic são ferramentas maduras e consolidadas há anos no mercado. A aplicação não precisa de abstrações teóricas que finjam que o ORM ou o framework web serão trocados.
- **Independência Modular Vertical**: Cada módulo funcional (fila, teleconsulta, identidade, triagem) deve ser auto-suficiente, desacoplado de detalhes internos dos outros módulos.
- **Testabilidade Ágil**: Possibilidade de testar regras de negócio e transições de estado diretamente nos modelos ricos em memória, sem necessidade de banco de dados ou mocks complexos.

---

## 3. Opções Consideradas

### Opção 1: Microsserviços Distribuídos
Decompor a aplicação em múltiplos serviços autônomos com gRPC/RabbitMQ.
- *Prós*: Escalabilidade independente de processos.
- *Contras*: Custo de infraestrutura inviável para municípios pequenos, overhead de rede, complexidade de observabilidade distribuída e gerenciamento de transações distribuídas (Sagas).

### Opção 2: Monólito Clássico com Modelos Anêmicos (Estilo MVC Tradicional)
Modelos de banco contendo apenas colunas de dados, com toda a lógica de negócio acumulada em roteadores ou em serviços procedurais gigantescos.
- *Prós*: Desenvolvimento inicial simplificado.
- *Contras*: "Big Ball of Mud", lógica de negócio dispersa e duplicada, código frágil e alta dificuldade de manutenção e testes unitários.

### Opção 3: Camadas Rígidas Teóricas com Entidades Puras Desacopladas
Separação de entidades puras em Python sem acoplamento ao ORM, com mapeamento bidirecional obrigatório em repositórios.
- *Prós*: Isolamento conceitual total do framework.
- *Contras*: Tributo altíssimo de boilerplate ("Mapper Hell"), perda dos recursos nativos do SQLAlchemy 2.0 (Identity Map, Unit of Work, dirty tracking automático) e complexidade de manutenção desproporcional para uma stack já consolidada.

### Opção 4: Monólito Modular Pragmático com Modelos Ricos no SQLAlchemy 2.0
Uma única base de código organizada em **fatias verticais modulares independentes**. Os modelos do SQLAlchemy 2.0 atuam como **Modelos Ricos** encapsulando estado e comportamento; repositórios encapsulam queries e persistência; serviços orquestram transações e chamadas; e a API FastAPI atua apenas como despachante de requisições:
- *Prós*: Sem conversões redundantes de dados; regras de negócio protegidas nos métodos do próprio modelo; pleno aproveitamento do SQLAlchemy 2.0 com tipagem estrita via `Mapped[...]`; testabilidade de métodos de domínio diretamente em memória; defensividade aplicada cirurgicamente apenas em gateways voláteis (LiveKit, PSCs, S3, Mensageria).
- *Contras*: Exige disciplina para manter o modelo rico e não permitir vazamento de lógica de negócio para os roteadores HTTP.

---

## 4. Decisão

Adotamos a **Opção 4: Monólito Modular Pragmático com Modelos Ricos no SQLAlchemy 2.0**.

### Diretrizes de Execução:
1. **Modelos Ricos (Rich Domain Models)**: Criados diretamente com a API declarativa do SQLAlchemy 2.0 (`Mapped[...]`). Métodos de transição de estado (como `alocar_para_chamada()`, `registrar_no_show()`, `validar_prescricao_digital()`) residem no próprio modelo, garantindo encapsulamento e proteção de invariantes.
2. **Camada de Repositório (`repository.py`)**: Encapsula todas as operações de banco (`select`, `execute`, queries complexas e clauses `execution_options`).
3. **Camada de Serviço (`service.py`)**: Orquestra transações do banco (`session.commit`), coordena repositórios, invoca métodos dos modelos ricos e integra com gateways externos voláteis.
4. **Camada de Apresentação Fina (`router.py`)**: Endpoints FastAPI recebem requisições, validam payloads via Pydantic (`schemas.py`), injetam dependências e chamam o serviço correspondente. Não contêm regras de negócio nem queries de banco.
6. **Independência Modular & Bounded Contexts**: Cada módulo atua como um Bounded Context do DDD, com sua própria linguagem ubíqua e modelos de negócio. Nenhum módulo acessa tabelas, repositórios ou modelos internos de outro módulo diretamente.
7. **Comunicação Inter-Modular em Memória**: A comunicação entre módulos no mesmo processo ocorre em memória com latência zero via duas estratégias:
   - *Chamada Síncrona a Serviços Públicos*: Um módulo injeta e invoca métodos da interface pública do `Service` de outro módulo, compartilhando a mesma transação assíncrona do banco (`session`).
   - *Eventos de Domínio em Memória (`In-Memory Domain Events`)*: Despacho assíncrono em memória para notificações desacopladas ("AtendimentoTriado", "ConsultaConcluida").
8. **Critério Estrito para Filas Externas (Valkey / ARQ)**: O tráfego só sai da memória para o Valkey/ARQ em dois cenários mandatários:
   - Concorrência atômica distribuída entre médicos (scripts Lua no Valkey).
   - Tarefas diferidas no tempo (Ring Timeout de 45 segundos via `_defer_by=45`) ou I/O externo lento com terceiros (WhatsApp, SMS, PSCs e S3).

---

## 5. Consequências

### Positivas:
- **Zero Mapper Hell**: Eliminação completa de camadas vazias de conversão entre entidades e modelos de banco.
- **Modelos Auto-Validáveis**: Invariantes clínicas e regulatórias são garantidas pelo próprio modelo, viabilizando testes unitários instantâneos em memória.
- **Produtividade Máxima**: Uso direto e idiomático do FastAPI, SQLAlchemy 2.0 e Pydantic v2.
- **Deploy Unificado**: A aplicação roda com um comando `docker compose up` em minutos.

### Negativas / Riscos Mitigados:
- *Risco de Regras Vazarem para o Router*: Mitigado por regras do linter que proíbem o roteador de importar repositórios ou executar queries diretamente, exigindo sempre a mediação do serviço.
