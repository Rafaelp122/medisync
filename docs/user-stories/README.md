# Catálogo de User Stories e Padrão de Inspeção da Qualidade

> **Versão da Especificação:** 1.1.0  
> **Referência de Domínio:** `docs/explanation/product-specification.md` e `docs/explanation/business-vision.md`  
> **Papel no Projeto:** Linha de Base Oficial de Qualidade Comportamental (Living Specification & Acceptance Gates)

---

## 1. Objetivo e Papel do Catálogo

Este diretório consolida a especificação comportamental dos **Requisitos de Produto (RF-01 a RF-10)** e **Invariantes Contratuais (RN01 a RN07)** do **MediSync Express**.

O catálogo cumpre três propósitos estruturais:
1. **Especificação Comportamental Viva (Living Spec):** Descreve em linguagem de negócio (*User Voice*) as jornadas reais dos usuários (pacientes, médicos, gestores) sem acoplamento a detalhes efêmeros de implementação.
2. **Critérios de Aceite Formais (BDD / Gherkin Puro):** Define cenários de *Dado / Quando / Então* focados na experiência e nas regras de negócio observáveis, servindo de base direta para testes funcionais e de integração.
3. **Padrão Oficial de Inspeção de Qualidade:** Cada história possui um checklist técnico objetivo mapeando os artefatos de código (rotas, serviços de aplicação, modelos de domínio, infraestrutura e testes automatizados) que garantem a entrega ponta a ponta (*Vertical Slice*).

---

## 2. Mapa das Personas

| Persona | Papel no Sistema | Principal Necessidade / Dor |
| :--- | :--- | :--- |
| **Juliana Silva** | Paciente espontânea (com dor/sintomas) | Acolhimento rápido (< 45s), transparência sobre sua vez na fila, login sem fricção de senhas e escape imediato em caso de piora clínica. |
| **Dr. Eduardo Rocha** | Médico plantonista | Zero overbooking de tela, alocação atômica justa (< 10ms), descarte rápido de no-show (45s), prontuário SOAP integrado e prescrição com salvaguardas legais. |
| **Patrícia Mendes** | Coordenadora de faturamento e regulação | Validação assíncrona de convênio/SUS sem travar o paciente, e fechamento contábil confiável pós-consulta sem glosas cadastrais. |
| **Carlos Drumond** | Diretor clínico e gestor operacional | Parametrização dinâmica do plantão (capacidade $\alpha$, médicos ativos) e telemetria operacional em tempo real (SLA $\ge 95\%$, TME e TMA real). |

---

## 3. Matriz Mestra de Rastreabilidade

O catálogo é estruturado entre **Jornadas Assistenciais e Operacionais Primárias** (fatias verticais que entregam valor direto para a persona) e **Políticas e Salvaguardas Transversais de Regra de Negócio** (regras que atuam como guardas de capacidade e exceções nas jornadas primárias):

### 3.1 Jornadas Assistenciais e Operacionais Primárias

| ID | Arquivo da Story | Requisito Base | Invariantes | Persona | Status de Conformidade no Código |
| :---: | :--- | :---: | :---: | :--- | :---: |
| **US-01** | [`US-01-acolhimento-triagem-tcle.md`](./US-01-acolhimento-triagem-tcle.md) | RF-01 | RN07, RN-REG-02 | Juliana Silva | 🟡 **Parcial** *(Omissão de `tcle_hash` no DTO de resposta)* |
| **US-02** | [`US-02-autenticacao-passwordless-otp.md`](./US-02-autenticacao-passwordless-otp.md) | RF-01 (#44) | RN-REG-02 | Juliana Silva | 🟢 **Conforme** |
| **US-03** | [`US-03-elegibilidade-onboarding-fase2.md`](./US-03-elegibilidade-onboarding-fase2.md) | RF-02 | RN03, RN-REG-02 | Juliana / Patrícia | 🟢 **Conforme** |
| **US-06** | [`US-06-deterioracao-clinica-escape-samu.md`](./US-06-deterioracao-clinica-escape-samu.md) | RF-06 | RN04, RN-REG-01 | Juliana Silva | 🟢 **Conforme** |
| **US-07** | [`US-07-alocacao-chamada-medica.md`](./US-07-alocacao-chamada-medica.md) | RF-03 | RN01, RN02 | Dr. Eduardo Rocha | 🟢 **Conforme** |
| **US-08** | [`US-08-atendimento-chamada-no-show.md`](./US-08-atendimento-chamada-no-show.md) | RF-03 | RN02, RN03 | Juliana / Eduardo | 🟢 **Conforme** |
| **US-09** | [`US-09-teleconsulta-pep-soap.md`](./US-09-teleconsulta-pep-soap.md) | RF-07 | RN06, RN-REG-01 | Dr. Eduardo Rocha | 🟢 **Conforme** |
| **US-10** | [`US-10-prescricao-assinatura-icp-brasil.md`](./US-10-prescricao-assinatura-icp-brasil.md) | RF-07 | Portaria 344/98 | Dr. Eduardo / Juliana | 🟢 **Conforme** |
| **US-11** | [`US-11-liquidacao-fechamento-contabil.md`](./US-11-liquidacao-fechamento-contabil.md) | RF-08 | RN-NEG-01 | Patrícia Mendes | 🔴 **Não Conforme** *(Issue #78: ausência de liquidação e BPA/TISS)* |
| **US-12** | [`US-12-parametrizacao-politicas-plantao.md`](./US-12-parametrizacao-politicas-plantao.md) | RF-09 | RN05 | Carlos Drumond | 🟢 **Conforme** |
| **US-13** | [`US-13-telemetria-painel-operacional.md`](./US-13-telemetria-painel-operacional.md) | RF-10 | RNF-10, SMART 1-5 | Carlos Drumond | 🟡 **Parcial** *(TTL ajustado para 5s - NC-TEL-01; gap remanescente: médico sem acesso ao painel - Issue #87)* |

### 3.2 Políticas e Salvaguardas Transversais de Regra de Negócio

| ID | Arquivo da Story | Requisito Base | Invariantes | Jornada Vinculada | Status | Função no Sistema |
| :---: | :--- | :---: | :---: | :--- | :---: | :--- |
| **US-04** | [`US-04-controle-admissao-backpressure.md`](./US-04-controle-admissao-backpressure.md) | RF-04 | RN05 | **US-01** (Admissão) & **US-12** (Gestão) | 🟢 **Conforme** | Salvaguarda estocástica ($\alpha$) e cota diária máxima impedindo superlotação da unidade. |
| **US-05** | [`US-05-regularizacao-elegibilidade-fila.md`](./US-05-regularizacao-elegibilidade-fila.md) | RF-05 | RN01, RN03 | **US-03** (Elegibilidade) | 🟢 **Conforme** | Fluxo de contingência assistencial e regularização preservando antiguidade na fila (NC-QUE-04). |

---

## 4. Padrão de Escrita e Inspeção de Qualidade

Ao consultar ou auditar uma história:
1. **Narrativa e Gherkin (Seções 1 e 2):** Descrevem puramente o valor de negócio e o comportamento esperado da persona, sem vazamento de detalhes mecânicos de banco de dados ou infraestrutura.
2. **Contrato de API (Seção 3):** Especifica a interface HTTP/REST ou WebSocket pública e canônica.
3. **Checklist de Inspeção (Seção 4):** Detalha os arquivos físicos, componentes técnicos (models, services, workers, adaptadores) e testes automatizados que validam a fatia vertical.
