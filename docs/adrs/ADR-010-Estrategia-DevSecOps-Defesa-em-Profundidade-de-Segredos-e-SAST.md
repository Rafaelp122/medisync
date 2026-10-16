# [ADR-010] Estratégia de DevSecOps — Defesa em Profundidade de Segredos e SAST em Camadas

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-10-15 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md), [ADR-006](ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md), [ADR-009](ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md), [CI/CD Strategy](../explanation/architecture/ci-cd-and-containers.md), [Security Architecture](../explanation/architecture/security-and-authorization.md) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** opera como uma plataforma de código aberto para Pronto-Atendimento Virtual (PA Digital 24/7). Por lidar com prontuários eletrônicos de pacientes (PEP), teleconsultas médicas e emissão de receitas assinadas digitalmente com certificados ICP-Brasil (PAdES-LTV), a plataforma está sujeita a regulamentações rigorosas de segurança, sigilo e privacidade:
* **Marco Regulatório**: Lei Geral de Proteção de Dados (LGPD - Lei nº 13.709/2018) e Resoluções CFM nº 1.821/2007 e nº 2.314/2022.
* **Ativos Críticos**: Chaves privadas de assinatura digital, tokens OAuth2 de PSCs (BirdID, SafeID, VIDaaS), segredos de sessão JWT, credenciais de storage S3/MinIO e chaves de API LiveKit SFU.

Após a entrega das configurações polimórficas por perfil ([ADR-009](ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md)), o repositório contava com validação *fail-fast* de segredos em runtime e checagens estáticas superficiais via Bandit (`tool.ruff.lint.select = ["S"]`). No entanto, remanesciam lacunas no ciclo de vida de desenvolvimento (SDLC):
1. **Risco de Vazamento de Segredos no Git**: Ausência de firewall automatizado pré-commit e no CI para impedir que tokens, senhas de ambiente e chaves privadas vazem acidentalmente para o histórico de commits do GitHub.
2. **Limitação de Análise Estática Superficial**: O linter Bandit realiza apenas correspondência sintática local (AST pattern matching), incapaz de realizar rastreamento profundo de fluxo de dados (*taint analysis*) entre parâmetros de requisições FastAPI e destinos sensíveis (banco de dados, storage e sistema operacional).
3. **Risco de Degradação do Fast CI**: A tentativa ingênua de rodar ferramentas pesadas de segurança ou suítes completas de integração no CI de Pull Requests aumentaria o tempo de feedback de segundos para múltiplos minutos, prejudicando o fluxo ágil e a produtividade da equipe.

---

## 2. Drivers de Decisão

* **Proteção Preventiva de Segredos**: Impedir commit e merge de qualquer credencial real de produção ou segredo criptográfico no repositório.
* **Governança de Dados Sintéticos e Fixtures Clínicas**: Permitir o uso legítimo de certificados mock, tokens efêmeros de teste e credenciais de desenvolvimento sem falsos-positivos bloqueantes.
* **Preservação da Disciplina do Fast CI**: Manter o tempo de resposta do CI de Pull Requests estritamente abaixo de 30 segundos, em conformidade com [docs/explanation/architecture/ci-cd-and-containers.md](../explanation/architecture/ci-cd-and-containers.md).
* **Análise SAST Avançada (Taint Tracking)**: Automatizar a detecção de vulnerabilidades complexas (OWASP Top 10, CWE, injeções, SSRF, path traversal) de forma desacoplada.
* **Ergonomia de Desenvolvimento e Compatibilidade com Agentes de IA**: Garantir que as verificações de segurança possam ser executadas localmente via automação padronizada (`justfile`), sem criar travas opacas que interfiram no ciclo de trabalho de desenvolvedores e agentes autônomos.

---

## 3. Opções Consideradas

### Opção 1: Dependência Exclusiva de Linters Sintáticos (Bandit/Ruff)
* Manter apenas as regras `S` do Ruff no `pyproject.toml`.
* *Contras*: O Bandit não detecta segredos arbitrários em arquivos de configuração, commits passados ou documentos, e não realiza análise de contaminação de variáveis (*taint analysis*). Insuficiente para conformidade em saúde.

### Opção 2: Esteira Monolítica Síncrona com SAST e Integração no Fast CI
* Executar testes de integração sobre contêineres Docker, CodeQL e Gitleaks em uma única esteira bloqueante a cada push.
* *Contras*: Elevaria o tempo de CI para 5 a 8 minutos por execução, violando os princípios de feedback ágil e fail-fast definidos na arquitetura.

### Opção 3: Esteira DevSecOps em Camadas Desacopladas (Adotada)
* **Camada 1 (Local / Pré-Commit)**: Hook de pre-commit opcional e comando local determinístico `just scan-secrets` (via binário nativo ou Docker).
* **Camada 2 (Fast CI no PR)**: Gitleaks executando em paralelo com os jobs de qualidade e testes unitários em memória (<15s), com `.gitleaks.toml` e `.gitleaksignore` calibrados.
* **Camada 3 (Deep SAST Assíncrono)**: GitHub CodeQL executando em pushes na `main`, schedule semanal e PRs com mutações em código-fonte (`src/**`), operando sob ambiente Python 3.12 estável.

---

## 4. Decisão

Adotamos a **Opção 3: Esteira DevSecOps em Camadas Desacopladas**.

### Diretrizes Mandatórias de Implementação:

1. **Firewall de Segredos com Gitleaks**:
   - O arquivo [`.gitleaks.toml`](../../.gitleaks.toml) estende as regras canônicas (`[extend] useDefault = true`) e define allowlists estruturadas para:
     - Diretórios de documentação e testes (`tests/**`, `docs/**`).
     - Exemplos de configuração pública (`.env.example`).
     - Prefixos canônicos de segredos sintéticos de desenvolvimento (`dev-insecure-.*`, `fake-.*`, `valid-oauth2-psc-token`).
   - O arquivo [`.gitleaksignore`](../../.gitleaksignore) registra fingerprints exatos de falsos-positivos em commits históricos.
   - O workflow [`.github/workflows/secret-scanning.yml`](../../.github/workflows/secret-scanning.yml) roda com `fetch-depth: 0` e bloqueia PRs que introduzam credenciais expostas.

2. **SAST Profundo com GitHub CodeQL**:
   - O workflow [`.github/workflows/codeql.yml`](../../.github/workflows/codeql.yml) é configurado para a linguagem Python com o conjunto `security-extended`.
   - Executa em Python 3.12 estável para garantir extração determinística da AST.
   - Acionado nos eventos de push para a branch `main`, em cron semanal e em PRs com alterações em `src/**` ou no próprio workflow de segurança.

3. **Automação Local e Pre-Commit**:
   - O comando `just scan-secrets` no [`justfile`](../../justfile) viabiliza a varredura instantânea de segredos no ambiente local, selecionando automaticamente o binário nativo ou contêiner Docker oficial.
   - O arquivo [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) integra saneamento de whitespace, validação de arquivos estruturados (YAML/TOML), Ruff do sistema e Gitleaks. A ativação no ambiente local é opt-in via `just pre-commit-install`.

4. **Preservação Irrestrita do Fast CI**:
   - Reafirma-se a diretriz de que testes de integração com I/O real e banco de dados relacional **não** rodam no Fast CI de Pull Requests, mantendo a segregação estrita entre testes unitários em memória e testes de integração com infraestrutura real.

---

## 5. Consequências e Trade-offs

### Consequências Positivas:
* **Blindagem Regulatória**: Redução drástica do risco de vazamento de credenciais clínicas, chaves de infraestrutura e tokens de acesso para o Git público.
* **Segurança de Fluxo de Dados**: Cobertura contínua contra vulnerabilidades do OWASP Top 10 através do CodeQL, auditadas diretamente na aba *Security* do GitHub.
* **Feedback Imediato Preservado**: O Fast CI permanece leve (~20s), enquanto a varredura profunda de SAST roda de forma assíncrona.
* **Reprodutibilidade Local**: Desenvolvedores e agentes de IA podem executar a auditoria de segredos com um único comando (`just scan-secrets`).

### Riscos Mitigados:
* **Falsos-Positivos em Fixtures Médicas**: Mitigados pela combinação de allowlists no `.gitleaks.toml` e registros pontuais no `.gitleaksignore`.
* **Incompatibilidade de Sintaxe no CodeQL**: Mitigada pela fixação do interpretador Python 3.12 no step de análise do CodeQL.

---

## 6. Rastreabilidade e Conformidade

* **Implementação**: Issue #80 (`ci(security): configurar pipeline de segurança com Gitleaks, CodeQL e pre-commit`).
* **Regulação**: LGPD (Lei nº 13.709/2018, Art. 46) e Resolução CFM nº 2.314/2022 (Segurança de Prontuário e Telemedicina).
