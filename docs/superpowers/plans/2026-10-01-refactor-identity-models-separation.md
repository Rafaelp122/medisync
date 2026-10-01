# Plano de Implementação — Refatoração e Modularização dos Modelos de Identidade

Este plano visa refatorar o módulo `identity` para desacoplar a lógica criptográfica da entidade clínica `Profissional`, quebrar o arquivo monolítico `models.py` em entidades isoladas por arquivo e consolidar a separação arquitetural entre **Identidade (Domínio Clínico)** e **Autenticação (Segurança/Infraestrutura)**.

---

## 🎯 Objetivos da Refatoração

1. **Separação de Entidades por Arquivo (SRP & Legibilidade):**
   * Substituir `src/modules/identity/domain/models.py` pelo pacote `src/modules/identity/domain/models/`.
   * Isolar cada agregado/entidade em seu arquivo:
     * `organizacao.py`
     * `profissional.py`
     * `paciente.py`
     * `dependente.py`
     * `_helpers.py` (funções auxiliares de sanitização/validação reutilizadas no domínio)
     * `__init__.py` (reexportação transparente de todos os modelos)
2. **Desacoplamento Criptográfico da Entidade `Profissional`:**
   * Remover métodos `set_password` e `verify_password` de `Profissional`.
   * A entidade armazena apenas seu estado (`senha_hash: str`) e oferece método puro de alteração de estado (`alterar_senha_hash(novo_hash: str)`).
   * Remover qualquer dependência de `src.core.security` dentro de `Profissional`.
   * A responsabilidade de hashear senhas e verificar credenciais permanece isolada em `src/core/security.py` e nos futuros casos de uso/serviços de autenticação (AuthN).
3. **Criação e Gestão de Issues no GitHub:**
   * Criar Issue de refatoração para rastreabilidade: `refactor(identity): modularize domain models and decouple password hashing`.
   * Criar Issue dedicada para Autenticação OWASP: `feat(auth): implement OWASP authentication service, Argon2id verification, rate limiting and JWT session management`.
4. **Preservação de Interfaces e Compatibilidade:**
   * Garantir que todas as importações públicas continuem funcionando através de `src.modules.identity.domain` ou `src.modules.identity.domain.models`.
   * Atualizar os testes unitários, testes de integração e factories.
   * Manter 100% de cobertura no módulo e 0 erros no `just check` (`basedpyright strict`, `ruff`, `tach check`).

---

## 🛠️ Mudanças Propostas

### 1. Domínio de Identidade (`src/modules/identity/domain/`)

#### [NEW] `src/modules/identity/domain/models/_helpers.py`
* Funções auxiliares de sanitização de dados cadastrais (ex.: `clean_digits(val: str) -> str`).

#### [NEW] `src/modules/identity/domain/models/organizacao.py`
* Entidade `Organizacao(Base)`:
  * Mapeamento relacional `organizacoes` (`BIGSERIAL`).
  * Invariantes de CNPJ (14 dígitos).
  * Métodos `is_sus()`, `ativar()`, `desativar()`.

#### [NEW] `src/modules/identity/domain/models/profissional.py`
* Entidade `Profissional(Base)` e tipo `PapelProfissional`:
  * Mapeamento relacional `profissionais` (`UUIDv7`).
  * Invariantes de CPF (11 dígitos).
  * Invariante CFM 2.314/2022: CRM e UF obrigatórios para médicos.
  * Método `alterar_senha_hash(novo_hash: str)` puro.
  * Métodos `is_medico()`, `ativar()`, `desativar()`.
  * **Sem acoplamento com `src.core.security` nem chamadas a Argon2id.**

#### [NEW] `src/modules/identity/domain/models/paciente.py`
* Entidade `Paciente(Base)`:
  * Mapeamento relacional `pacientes` (`UUIDv7`).
  * Invariantes de CPF e CNS (suporte pediátrico/SUS).
  * Gestão de alergias em `JSONB` (`adicionar_alergia`, `remover_alergia`, `tem_alergia`).
  * Regra de idade clínica `is_pediatrico()`.

#### [NEW] `src/modules/identity/domain/models/dependente.py`
* Entidade `Dependente(Base)`:
  * Mapeamento relacional `dependentes` (`UUIDv7`).
  * Invariante anti-reflexiva (`titular_id != dependente_id`).
  * Vínculo de menor/tutelado.

#### [NEW] `src/modules/identity/domain/models/__init__.py`
* Reexporta `Organizacao`, `Profissional`, `Paciente`, `Dependente` e `PapelProfissional`.

#### [DELETE] `src/modules/identity/domain/models.py`
* Removido e substituído pelo pacote `models/`.

#### [MODIFY] `src/modules/identity/domain/__init__.py`
* Mantém reexportação limpa a partir do novo pacote `src.modules.identity.domain.models`.

---

### 2. Testes e Factories

#### [MODIFY] `tests/factories/identity.py`
* Manter geração com `senha_hash` default configurável.

#### [MODIFY] `tests/unit/test_identity_models.py`
* Adaptar o teste de senha para validar `prof.alterar_senha_hash(novo_hash)` em vez de chamar criptografia direta na entidade.
* Testes de validação de modelo permanecem intactos.

#### [MODIFY] `tests/integration/test_identity_persistence.py`
* No teste de persistência do profissional, utilizar `hash_password("Argon2SecurePassword")` da camada de segurança para fornecer o hash pronto à entidade, validando com `verify_password` externo.

---

### 3. Gestão de Rastreabilidade no GitHub

#### [NEW] Issue no GitHub: `refactor(identity): modularize domain models and decouple password hashing`
* Rastreia a refatoração do módulo `identity`, modularização de arquivos e desacoplamento do Argon2id de `Profissional`.

#### [NEW] Issue no GitHub: `feat(auth): implement OWASP authentication service, Argon2id verification, rate limiting and JWT session management`
* Rastreia o módulo e serviço dedicado de Autenticação aderente ao OWASP Authentication Cheat Sheet.

---

## 🧪 Plano de Verificação

### 1. Testes Automatizados Unitários e de Integração
```bash
# Testes unitários dos modelos modularizados
uv run pytest tests/unit/test_identity_models.py -v

# Testes de persistência e integridade relacional no PostgreSQL 17
uv run pytest tests/integration/test_identity_persistence.py -v

# Todas as suítes de teste
uv run pytest
```

### 2. Portão de Qualidade Completo (`just check`)
```bash
just check
```
Critérios de aceitação:
- [ ] `ruff format .` sem alterações necessárias.
- [ ] `ruff check . --fix` com 0 erros e 0 warnings.
- [ ] `basedpyright` em modo estrito (`strict`) com 0 erros e 0 avisos.
- [ ] `tach check` validando fronteiras modulares limpas (sem violação de camadas).
- [ ] 100% de cobertura nos novos arquivos em `src/modules/identity/domain/models/`.
- [ ] 72+ testes passando no `pytest`.
