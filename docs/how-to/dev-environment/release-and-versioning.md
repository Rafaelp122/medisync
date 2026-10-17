# Como Operar o Versionamento Semântico e Release Automatizado

> Guia operacional para redação de commits convencionais, simulação de bumps de versão e publicação automatizada de releases.

---

## Contexto

O MediSync Express adota **Versionamento Semântico (SemVer 2.0.0)** orquestrado via **Commitizen** e integrado ao pipeline do GitHub Actions (`.github/workflows/release.yml`). 

Cada merge na branch `main` calcula automaticamente o próximo incremento de versão, atualiza o arquivo `CHANGELOG.md`, sincroniza a versão no `pyproject.toml` e em `src/core/config.py`, e gera uma Git Tag anotada com uma GitHub Release correspondente.

---

## Pré-requisito Obrigatório no GitHub

Para que o GitHub Actions consiga realizar o push da tag e do commit de bump na branch `main`, as permissões do repositório no GitHub devem estar configuradas:

1. Acesse o repositório no GitHub: `Settings` $\to$ `Actions` $\to$ `General`.
2. Role até a seção **Workflow permissions**.
3. Selecione a opção **"Read and write permissions"**.
4. Marque a caixa de seleção **"Allow GitHub Actions to create and approve pull requests"**.
5. Clique em **Save**.

---

## Passo a Passo Operacional

### 1. Redigir Commits no Padrão Conventional Commits

Todas as mensagens de commit devem seguir o padrão formal [Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>(<escopo opcional>): <descrição no imperativo e em minúsculas>
```

#### Tabela de Impacto no Versionamento

| Tipo | Descrição | Impacto no SemVer | Exemplo |
| :--- | :--- | :---: | :--- |
| `feat` | Nova funcionalidade para o usuário | **MINOR** (`0.1.0` $\to$ `0.2.0`) | `feat(queue): adicionar cota diaria no valkey` |
| `fix` | Correção de bug no código produtivo | **PATCH** (`0.1.0` $\to$ `0.1.1`) | `fix(auth): corrigir retorno 429 em tentativas otp` |
| `perf` | Melhoria de desempenho | **PATCH** (`0.1.0` $\to$ `0.1.1`) | `perf(lua): otimizar script de alocacao atomica` |
| `refactor` | Refatoração sem alteração de comportamento | **PATCH** (`0.1.0` $\to$ `0.1.1`) | `refactor(app): transformar main em composition root` |
| `docs` | Alterações exclusivas na documentação | Sem bump | `docs(api): documentar contratos de fila` |
| `test` | Adição ou correção de testes | Sem bump | `test(unit): adicionar testes para fila de prioridade` |
| `chore` | Manutenção de tooling e dependências | Sem bump | `chore(deps): atualizar dependencias com uv` |
| `!` ou `BREAKING CHANGE:` | Mudança incompatível na API | **MAJOR** (`0.1.0` $\to$ `1.0.0`) | `feat(api)!: reestruturar payload de admissao` |

> [!NOTE]
> Enquanto o sistema estiver em versão inicial (`0.x.y`), o Commitizen respeita a diretiva `major_version_zero = true` no `.cz.toml`, tratando mudanças de quebra como incremento de `MINOR` para preservar a estabilidade da fase de homologação.

---

### 2. Simular o Próximo Bump Localmente (`bump-check`)

Antes de abrir ou mergear um Pull Request, simule qual será o impacto semântico dos seus commits:

```bash
just bump-check
```

O comando executará `uv run cz bump --dry-run --check-consistency` e exibirá:
- A versão atual e a nova versão calculada;
- A tag Git que será criada (ex.: `v0.2.0`);
- A prévia do trecho do `CHANGELOG.md` gerado automaticamente.

---

### 3. Abrir e Mergear o Pull Request

Ao trabalhar em uma branch de funcionalidade ou correção:

1. **Título do PR:** Dê ao Pull Request um título estritamente convencional (ex.: `fix(ci): ativar pipeline de release semantico automatizado`).
2. **Estratégia de Merge:**
   - **Squash and Merge:** O título do PR se torna a mensagem do commit único enviado para a `main`. Certifique-se de que o título do PR está com o prefixo correto (`feat:`, `fix:`, etc.).
   - **Rebase and Merge:** Preserva os commits individuais da branch. Todos os commits convencionais serão lidos pelo Commitizen.
3. **Disparo do Release:** Ao concluir o merge na `main`, o workflow `.github/workflows/release.yml` é executado automaticamente.

---

### 4. Executar Bump Localmente (Procedimento de Manutenção)

Caso seja necessário gerar uma versão semântica manualmente fora do GitHub Actions:

```bash
just bump
```

O comando executará `uv run cz bump --changelog --check-consistency`, atualizando localmente os arquivos `pyproject.toml`, `src/core/config.py`, `CHANGELOG.md` e criando a tag Git anotada.

---

## Verificação e Auditoria da Versão

Para auditar qual versão está em execução em um ambiente implantado:

1. Consulte o endpoint de integridade operacional:
   ```bash
   curl -s http://localhost:8000/healthz | jq .
   ```
2. O payload JSON exibirá a versão sincronizada:
   ```json
   {
     "status": "healthy",
     "version": "0.2.0",
     "services": {
       "database": "connected",
       "valkey": "connected"
     }
   }
   ```

---

## Ver Também

- [CI/CD Strategy & Container Architecture](../../explanation/architecture/ci-cd-and-containers.md)
- [Setup Local](setup-local.md)
- [Run Tests](../backend/run-tests.md)
