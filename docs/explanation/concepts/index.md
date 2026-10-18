# Conceitos de Arquitetura

> Padrões de design, mecanismos de concorrência e invariantes transversais explicados em profundidade.

Os conceitos canônicos documentam o funcionamento interno do **MediSync Express**, detalhando como os padrões de isolamento, injeção de dependências e concorrência operam em harmonia nos módulos do sistema.

Esta documentação serve como referência explicativa (quadrante *Explanation* do Diátaxis) para apoiar desenvolvedores e agentes na manutenção da integridade estrutural da base de código.

---

## Índice dos Conceitos Canônicos

### 1. [Composition Root e Injeção de Dependências](composition-root-and-dependencies.md)
- **Papel:** Centraliza a montagem do grafo de dependências nas raízes de composição de cada módulo.
- **Sinopse:** Elimina variáveis globais mutáveis e isola adaptadores de infraestrutura. Assegura que routers consumam dependências tipadas via `*Dep` e que serviços de aplicação nunca importem configurações de ambiente.

### 2. [Hexagonal Pragmático sem Mapper Hell](hexagonal-pragmatico.md)
- **Papel:** Estabelece entidades ricas e elimina duplicação desnecessária de camadas de conversão.
- **Sinopse:** Modela entidades SQLAlchemy 2.0 com métodos de domínio ricos e regras clínicas encapsuladas. Schemas Pydantic operam exclusivamente na borda de apresentação com validação e hidratação automática via `from_attributes`.

### 3. [Protocolos e Contratos Inter-Módulos](inter-module-protocols.md)
- **Papel:** Desacopla a comunicação síncrona entre módulos verticais independentes.
- **Sinopse:** Define portas públicas através de `typing.Protocol` (PEP 544) e transferência de dados via DTOs imutáveis. Proíbe a importação cruzada de entidades, tabelas e repositórios entre módulos.

### 4. [Multi-Tenancy e Isolamento PostgreSQL RLS](multi-tenancy-rls.md)
- **Papel:** Aplica isolamento de tenant defensivo em nível de banco de dados relacional.
- **Sinopse:** Impõe barreiras de segurança física com Row-Level Security (`FORCE ROW LEVEL SECURITY`) e papéis restritos. Garante que nenhum dado transacional vaze entre organizações, mesmo diante de falha acidental de filtros da aplicação.

### 5. [Concorrência de Fila com Lua e Worker ARQ](queue-lua-arq.md)
- **Papel:** Executa ordenação clínica em tempo real e convocação atômica de pacientes.
- **Sinopse:** Combina ordenação por score com scripts Lua no Valkey para garantia de exclusão mútua e tempo de resposta submilisegundo. Workers ARQ processam tarefas pesadas e descarte de no-show em segundo plano.

---

## Salvaguardas e Verificação Contínua

A integridade destes conceitos é garantida por testes arquiteturais automatizados e checagens estáticas:

- `just tach` — Valida as fronteiras modulares e impede acoplamentos não autorizados.
- `just typecheck` — Executa checagem estrita de tipos com `basedpyright`.
- `tests/architecture/test_routers_are_thin.py` — Garante que routers permaneçam finos e deleguem lógica.
- `tests/architecture/test_services_and_composition.py` — Audita o desacoplamento de configurações nos serviços.
- `tests/architecture/test_main_composition_root.py` — Valida a composição enxuta do ponto de entrada principal.
