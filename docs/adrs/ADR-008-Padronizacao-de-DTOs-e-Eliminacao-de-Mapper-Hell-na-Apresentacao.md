# [ADR-008] Padronização de DTOs e Eliminação de Mapper Hell na Apresentação

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-10-04 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md), [Overview de Arquitetura](../03-architecture/overview.md) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** estabeleceu na [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md) a eliminação do *Mapper Hell* entre as entidades de Domínio e os modelos ORM de persistência (SQLAlchemy 2.0).

Contudo, observou-se uma proliferação de classes duplicadas e conversões manuais repetitivas entre a camada de **Apresentação** (`schemas.py` / Pydantic) e a camada de **Aplicação** (`dtos.py` ou dentro dos serviços / `@dataclass(frozen=True)`):
1. **Estruturas Espelho 1:1**: Criação de `XRequest` (Pydantic) e `XInputDTO` (`dataclass`) com os mesmos atributos e tipos exatos, forçando os roteadores FastAPI a escrever blocos extensos de mapeamento campo a campo.
2. **Serialização Manual de Respostas**: Em vez de aproveitar recursos declarativos modernos do Pydantic v2 (`from_attributes=True`), roteadores copiavam manualmente de 10 a 20 campos de entidades SQLAlchemy ou DTOs para modelos de resposta.
3. **Dispersão e Inconsistência de Arquivos**: DTOs declarados inline no meio de arquivos de serviço (`onboarding_service.py`, `dependente_service.py`, `triage_service.py`) e schemas Pydantic declarados diretamente dentro de arquivos de roteador (`consultation_router.py`), inflando-os desnecessariamente.

---

## 2. Drivers de Decisão

* **Eliminação de Código Redundante e Boilerplate**: Reduzir a carga de manutenção, o risco de erros de digitação e a fricção no desenvolvimento diário (DX).
* **Aproveitamento Pleno do Pydantic v2**: O Pydantic v2 (implementado em Rust) possui desempenho de ponta e suporte a imutabilidade (`frozen=True`) e carregamento automático a partir de atributos de objetos Python/ORM (`from_attributes=True`).
* **Preservação do Desacoplamento onde há Enriquecimento de Contexto**: Manter objetos de comando (`Command`) explícitos sempre que o caso de uso exigir a fusão de dados de origens distintas (ex.: Path Params, Headers HTTP, Socket IP e Body JSON).
* **Consistência Estrutural Rígida**: Padronização dos locais de definição de esquemas e DTOs em todos os módulos em `src/modules/*`.

---

## 3. Opções Consideradas

### Opção 1: Manter DTOs e Schemas Estritamente Separados em 100% dos Casos
* Cria-se um `DTO` e um `Schema` para cada rota, sempre mapeando manualmente no roteador.
* *Prós*: Separação purista teórica de camadas.
* *Contras*: Alto atrito de desenvolvimento (*Mapper Hell*), redundância massiva de código e risco contínuo de dessincronização entre atributos.

### Opção 2: Eliminar Completamente DTOs e Usar Pydantic Diretamente no Domínio
* Usar modelos Pydantic no lugar de entidades SQLAlchemy no domínio.
* *Prós*: Apenas uma representação de dados.
* *Contras*: Fere a [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md), perde o Unit of Work do SQLAlchemy e gera modelos anêmicos.

### Opção 3: Padronização Pragmática de DTOs e Schemas com Pydantic v2 (Adotada)
* Unificar entradas simples com schemas Pydantic imutáveis (`frozen=True`).
* Utilizar `Command` em `application/dtos.py` apenas quando houver enriquecimento contextual.
* Utilizar `ConfigDict(from_attributes=True)` e `model_validate()` para serialização automática de respostas.
* Centralizar schemas em `presentation/schemas.py` e DTOs em `application/dtos.py`.

---

## 4. Decisão

Adotamos a **Opção 3: Padronização Pragmática de DTOs e Schemas com Pydantic v2**.

### Diretrizes Mandatórias de Implementação:

1. **Entradas (Inputs / Requests)**:
   * **Cenário Direto (1:1)**: Se os dados necessários para o caso de uso vêm inteiramente do corpo da requisição JSON, o schema Pydantic (com `ConfigDict(frozen=True, str_strip_whitespace=True)`) é utilizado diretamente como tipo de entrada do serviço de aplicação. Proíbe-se a criação de DTO espelho duplicado.
   * **Cenário de Enriquecimento (Commands)**: Se o caso de uso precisa combinar dados de múltiplas origens (Path Parameters, Headers HTTP de Tenant, Endereço IP do cliente e Body), define-se um `@dataclass(frozen=True)` nomeado com sufixo `Command` em `application/dtos.py`. O roteador compõe o `Command` e o envia ao serviço.

2. **Saídas (Outputs / Responses)**:
   * Todos os modelos Pydantic de resposta em `presentation/schemas.py` devem declarar `model_config = ConfigDict(from_attributes=True)`.
   * A conversão a partir de entidades ricas do SQLAlchemy ou DTOs de resultado deve ser feita exclusivamente via `ResponseSchema.model_validate(objeto)` ou delegação declarativa ao FastAPI (`response_model=ResponseSchema`).
   * É **terminantemente proibido** realizar mapeamentos manuais campo a campo (`id=entidade.id, nome=entidade.nome, ...`).

3. **Organização Física Obrigatória**:
   * **`src/modules/<modulo>/presentation/schemas.py`**: Arquivo exclusivo para todos os schemas Pydantic de apresentação daquele módulo.
   * **`src/modules/<modulo>/application/dtos.py`**: Arquivo exclusivo para Commands e DTOs puros da aplicação daquele módulo.
   * Proíbe-se a declaração de DTOs inline em arquivos de serviço e de schemas Pydantic inline em arquivos de roteador.

---

## 5. Consequências

### Positivas:
* **Eliminação Total do Mapper Hell**: Desaparecimento de centenas de linhas de código repetitivo nos roteadores.
* **Manutenção Eficiente (DX)**: Adicionar um novo campo no contrato de uma rota requer alteração apenas no schema e no consumidor final, sem camadas intermediárias inúteis.
* **Arquivos Limpos e Coesos**: Roteadores tornam-se enxutos, focados apenas em orquestração HTTP, tratamento de status codes e injeção de dependências.
* **Preservação de Desacoplamento**: Serviços continuam protegidos e desacoplados de transporte HTTP onde a lógica de comando realmente exige.

### Riscos Mitigados:
* *Risco de Acoplamento Indevido de Schemas com Domínio*: Mitigado pelo uso de `from_attributes=True` na camada de apresentação; o domínio e as entidades SQLAlchemy permanecem desconhecedores da existência do Pydantic.
