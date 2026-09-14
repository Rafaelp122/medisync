# Especificação de Requisitos de Software (SRS)

## MediSync Express — Plataforma de Código Aberto para Pronto-Atendimento Virtual (PA Digital 24/7)

| Atributo | Detalhamento |
| :--- | :--- |
| **Referencial Metodológico** | Engenharia de Requisitos — Software Orientado ao Negócio (Vazquez & Simões) |
| **Marco Regulatório & Ético** | Resolução CFM nº 2.314/2022 \| LGPD (Lei Federal nº 13.709/2018 - Art. 11) |
| **Padrões de Acessibilidade** | Diretrizes de Acessibilidade para Conteúdo Web (WCAG 2.1 Nível AA) |
| **Modelo de Licenciamento** | Código Aberto Permissivo (OSI - Licença MIT ou Apache 2.0) |
| **Versão & Status** | Versão 1.0 (Homologada: Salvaguardas Clínicas, TCLE Criptográfico, Deadlock Prevention e Acessibilidade) |

---

## 1. Contextualização e Declaração do Problema (Domínio do Problema)

### 1.1 Visão Geral e Justificativa de Negócio
O **MediSync Express** é uma plataforma de código aberto concebida para viabilizar unidades de Pronto-Atendimento Virtual (PA Digital 24/7) para demandas de saúde de baixa e média complexidade clínica, operando sob regime de demanda espontânea (sem agendamento prévio). Conecta pacientes com sintomas agudos a médicos plantonistas generalistas ou de família em ambiente seguro e auditável.

A solução adota arquitetura altamente parametrizável, atendendo desde pequenos municípios e unidades básicas do SUS até cooperativas médicas, planos de autogestão e operadoras privadas. A jornada do paciente e da equipe assistencial organiza-se na seguinte esteira de valor:

```mermaid
flowchart LR
    A["Acolhimento & Triagem Estruturada<br/>(com TCLE Digital)"] --> B["Fila Dinâmica com<br/>Salvaguarda de Deterioração"]
    B --> C["Validação Assíncrona<br/>de Elegibilidade"]
    C --> D["Teleconsulta Integrada<br/>(PEP + Assinatura ICP-Brasil)"]
    D --> E["Telemetria Operacional &<br/>Trilha Append-Only"]
```

> **📌 ESTEIRA DE ATENDIMENTO INTEGRAL**  
> Acolhimento & Triagem Estruturada (com TCLE Digital) ➔ Fila Dinâmica com Salvaguarda de Deterioração ➔ Validação Assíncrona de Elegibilidade ➔ Teleconsulta Integrada (PEP + Assinatura ICP-Brasil) ➔ Telemetria Operacional & Trilha Append-Only

### 1.2 Declaração do Problema (Modelo Canvas de Requisitos)
- **Problema Oportunizado**: Inexistência de uma infraestrutura aberta, modular, auditável e juridicamente segura para pronto-atendimento virtual que permita a instituições públicas e privadas operar filas dinâmicas em tempo real, mitigando o colapso por burnout de equipes médicas e garantindo faturamento sem erguer barreiras desumanizadas de entrada.
- **Partes Afetadas**: Pacientes com queixas clínicas agudas, Médicos Plantonistas, Equipes de Regulação/Faturamento e Administradores de Operações em Saúde.
- **Impacto Observado**: Superlotação crônica em emergências físicas; exaustão de médicos submetidos a filas infinitas sem teto de saturação; risco de glosas e atendimentos não faturáveis; risco de eventos adversos na fila de espera por deterioração clínica silenciosa; e inviabilidade financeira de adoção de telemedicina por entidades com orçamento restrito.
- **Critérios de Sucesso da Solução**: Disponibilizar acolhimento padronizado com aceite explícito de TCLE e triagem parametrizável com desvio mandatório de emergências (SAMU 192); salvaguarda de piora clínica na fila de espera; controle de admissão (backpressure com margem estocástica $\alpha$); prevenção estrita de deadlocks e overbooking; preservação irrevogável do ato médico; e aderência universal de acessibilidade digital (WCAG 2.1 AA).

### 1.3 Objetivos de Negócio e Metas SMART (Instância Padrão)
- **S (Específico)**: Disponibilizar uma base open source de PA Digital com motor de alocação atômica em memória, pipeline concorrente de liquidação/elegibilidade, salvaguardas de deterioração clínica, governança médica e painel de telemetria.
- **M (Mensurável)**: Garantir cumprimento do SLA parametrizado (meta padrão: 95% atendidos na meta de sua prioridade); reordenação de fila $\le 200\text{ ms}$; taxa de glosas cadastrais $< 0{,}5\%$; tolerância a chamadas sem resposta com ring timeout de 45 segundos; e latência de telemetria $< 5\text{ s}$.
- **A (Alcançável)**: Foco delimitado a urgências de atenção primária e baixa/média gravidade, delegando emergências críticas com risco de vida imediatamente ao socorro pré-hospitalar.
- **R (Relevante)**: Conformidade integral com a Resolução CFM nº 2.314/2022, Lei Geral de Proteção de Dados (LGPD - Art. 11), normas de interoperabilidade em saúde e proteção da autonomia médica.
- **T (Tempestivo)**: Arquitetura modular pragmática com modelos ricos no ORM, repositório documentado sob o padrão Diátaxis e orquestração automatizada para rápida implantação.

---

## 2. Partes Interessadas, Personas e Matriz de Necessidades

### 2.1 Personas do Sistema
- **Juliana Silva (Paciente / Responsável Familiar)**: 34 anos. Mãe de um filho de 4 anos e também usuária própria do PA Digital. Busca acolhimento imediato para febre alta e sintomas agudos (próprios ou do dependente). Exige clareza de posicionamento na fila, fluxo de entrada sem atrito burocrático na urgência (< 45s), facilidade para declarar dependentes menores, termos de consentimento transparentes, interface acessível no celular e mecanismo rápido de socorro caso haja piora súbita enquanto aguarda.
- **Dr. Eduardo Rocha (Médico Plantonista)**: 42 anos. Especialista em Medicina de Família. Exige ambiente único (vídeo + prontuário + emissão com ICP-Brasil), proteção contra sobreposição de consultas (zero overbooking), desobstrução imediata de tela caso o paciente chamado não atenda (no-show) e respeito irrestrito ao seu tempo clínico sem quedas forçadas.
- **Patrícia Mendes (Gestora de Faturamento / Regulação)**: 38 anos. Precisa de garantia de autorização prévia de cobertura ou retenção particular antes da efetivação da teleconsulta, eliminando custos não faturáveis e glosas cadastrais.
- **Carlos Drumond (Gestor de Operações / Administrador)**: 29 anos. Responsável pelo dimensionamento e infraestrutura. Precisa parametrizar tetos de admissão, SLAs, margens de segurança ($\alpha$) e perfis operacionais (ex.: SUS vs. Privado), acompanhando telemetria contínua para evitar sobrecarga da equipe médica.

### 2.2 Matriz de Necessidades Declaradas

| ID | Necessidade Declarada | Persona | Condição de Aceite no Negócio |
| :--- | :--- | :--- | :--- |
| **NEC-01** | Acolhimento ágil com cadastro progressivo e TCLE | Juliana | Entrada em $< 45\text{ s}$ com pré-anamnese e TCLE para inserção imediata na fila, permitindo completar dados clínicos e endereço na fila de espera. |
| **NEC-02** | Atendimento no SLA com botão de socorro na fila | Juliana | Chamada dentro da meta de gravidade e canal de escape imediato caso sinta piora súbita dos sintomas. |
| **NEC-03** | Acessibilidade e usabilidade inclusiva | Juliana | Navegação amigável em dispositivos móveis sob critérios de contraste e áreas de toque WCAG 2.1 AA. |
| **NEC-04** | Interface sem concorrência e sem travamentos | Dr. Eduardo | Zero overbooking; liberação de tela em 45 s caso paciente não atenda (no-show); teto rígido de fila. |
| **NEC-05** | PEP integrado com assinatura digital válida | Dr. Eduardo | Videochamada WebRTC, evolução clínica e emissão com certificado ICP-Brasil em painel unificado. |
| **NEC-06** | Validação financeira assíncrona | Patrícia | Autorização de convênio ou hold de cartão confirmados em segundo plano antes da abertura da sala médica. |
| **NEC-07** | Parametrização operacional flexível e perfis | Carlos | Ajuste de SLAs, cotas, TMA, fator $\alpha$ e alternância limpa entre perfis de deploy (SUS vs. Convênios). |
| **NEC-08** | Telemetria operacional e governança clínica | Carlos | Painel em tempo real de ocupação médica, SLAs, abandonos e trilha imutável append-only de eventos. |

---

## 3. Restrições e Premissas do Projeto

### 3.1 Restrições Regulatórias e de Negócio
- **RN-REG-01 (Conformidade CFM nº 2.314/2022 e Respeito ao Ato Médico)**: A triagem automatizada do sistema tem caráter estritamente orientativo e de apoio à decisão clínica. O médico assistente possui soberania diagnóstica e terapêutica irrevogável para ratificar ou alterar a classificação ao abrir o atendimento. É expressamente proibido que a plataforma encerre ou desconecte teleconsultas por critério temporal.
- **RN-REG-02 (Privacidade, LGPD Art. 11, Identificação CFM e TCLE Obrigatório)**: Tratando-se de dados sensíveis de saúde, o ingresso no pronto-atendimento exige coleta obrigatória e explícita do Termo de Consentimento Livre e Esclarecido (TCLE) com registro de versão, consentimento de teleatendimento e política de privacidade. Para conformidade com as Resoluções CFM nº 1.821/2007 e 2.314/2022, o prontuário deve conter obrigatoriamente: identificação civil (nome completo, nome social se houver, sexo biológico, data de nascimento), nome da mãe (chave de desambiguação CADSUS/Receita Federal) e endereço completo com CEP (mandatório para envio de socorro de emergência via SAMU 192 e prescrição). Em atendimentos pediátricos ou de incapazes, o responsável legal é formalmente identificado e assume a outorga do TCLE.
- **RN-REG-03 (Neutralidade e Abertura de Protocolos Clínicos)**: O software é terminantemente desvinculado de protocolos proprietários com direitos autorais restritos (como o Manchester Triage System). A categorização de gravidade adota taxonomia neutra aberta parametrizável em níveis e cores, viabilizando o protocolo de Acolhimento e Classificação de Risco do SUS ou matrizes institucionais próprias.
- **RN-NEG-01 (Fluxo Financeiro Não Obstrutivo)**: O paciente é acolhido e inserido na fila de triagem sem bloqueios de pagamento na tela inicial. A validação ocorre em background; a transição para sala ativa, contudo, é estritamente condicionada à confirmação de elegibilidade ou deferimento de contingência.
- **RN-NEG-02 (Licenciamento Open Source Permissivo)**: O núcleo funcional da aplicação é distribuído sob licença livre permissiva reconhecida pela OSI (MIT ou Apache 2.0), utilizando arquitetura de portas e adaptadores para desacoplar conectores proprietários de faturamento e mensageria.

### 3.2 Premissas do Projeto
- **PREM-01 (Serviços de Mídia e Sinalização em Tempo Real)**: A instituição mantenedora da instância provê ou contrata serviços de sinalização e roteamento de mídia (servidor SFU WebRTC) homologados para suporte a streaming criptografado.
- **PREM-02 (Certificação Digital de Profissionais)**: Os médicos plantonistas ativos dispõem de certificados digitais válidos e compatíveis com a Infraestrutura de Chaves Públicas Brasileira (ICP-Brasil), operando via nuvem ou dispositivos criptográficos.
- **PREM-03 (Escala Médica e Dimensionamento da Unidade)**: A instituição operadora estabelece e gerencia ativamente a quantidade de médicos em plantão, calibrando a capacidade de absorção de acordo com a demanda esperada.

---

## 4. Requisitos Funcionais (Nível de Objetivo do Usuário)

- **RF-01: Realizar Acolhimento, Triagem Estruturada e TCLE Digital (Cadastro Progressivo - Fase 1)**: O usuário declara se o atendimento é próprio ou para dependente/filho, informa CPF, data de nascimento e telefone celular (com validação OTP), queixa principal, tempo de evolução, escala de dor e sinais de alerta, concedendo aceite formal explícito ao TCLE e à política de privacidade. O motor calcula a prioridade clínica preliminar, vincula o hash do termo aceito ao cadastro e insere o atendimento na Fila Dinâmica com status `TRIADO_AGUARDANDO_ELEGIBILIDADE`.
- **RF-02: Executar Validação de Elegibilidade e Enriquecimento Cadastral (Cadastro Progressivo - Fase 2)**: Em paralelo à permanência do paciente na fila, workers em background consultam a cobertura junto à operadora de saúde (ou efetuam no-op no SUS) enquanto a interface conduz o paciente no preenchimento dos dados complementares exigidos pelo CFM: nome completo, nome da mãe, sexo biológico, endereço com CEP (para emergência/SAMU) e histórico de alergias medicamentosas. Concluídos a elegibilidade e o enriquecimento, o status transiciona automaticamente para `APTO_PARA_CHAMADA`.
- **RF-03: Realizar Chamada, Habilitação de Atendimento e Tratamento de No-Show**: O sistema (ou o médico ao clicar em 'Chamar Próximo') aloca o paciente com status `APTO_PARA_CHAMADA` de maior prioridade clínica. O sistema aciona um aviso sonoro/visual na tela do paciente e inicia contagem regressiva de chamada (ring timeout de 45 s). Se o paciente atender, a sala WebRTC e o PEP são abertos simultaneamente; caso não responda no tempo limite, o atendimento é marcado como `PACIENTE_AUSENTE` e o médico é liberado imediatamente para nova chamada, evitando deadlocks.
- **RF-04: Gerenciar Fila Dinâmica e Controle de Admissão (Backpressure)**: O sistema monitora a carga em tempo real. Se o volume acumulado de espera ultrapassar a capacidade segura da escala restante (com fator de segurança $\alpha$) ou a cota diária máxima for atingida, novas admissões são bloqueadas preventivamente com mensagem informativa, disparando evento de notificação de transbordo assistencial.
- **RF-05: Tratar Exceções e Falhas de Elegibilidade na Fila**: Em caso de timeout ou recusa na validação financeira, o paciente é notificado em sua tela de espera para regularizar o meio de pagamento ou solicitar contingência administrativa, preservando rigorosamente sua prioridade clínica na esteira de triagem.
- **RF-06: Monitorar Deterioração Clínica na Fila de Espera (Escape de Emergência)**: A interface de espera do paciente deve exibir de forma destacada e acessível a funcionalidade 'Sentiu piora nos sintomas?'. O acionamento permite ao paciente responder a checagem rápida de sinais de alarme: constatada emergência, o sistema desvia imediatamente para instrução de socorro urgente (SAMU 192) e emite alerta prioritário no painel de controle da unidade.
- **RF-07: Conduzir Teleconsulta, Registrar PEP e Assinar Receituário**: O médico conduz a teleconsulta via áudio/vídeo, consulta dados de acolhimento, preenche evolução clínica e emite documentos médicos (receitas, atestados e pedidos de exames) com assinatura digital ICP-Brasil integrada.
- **RF-08: Concluir e Liquidar Atendimento**: Mediante encerramento formal da consulta no PEP pelo médico assistente, o sistema registra a finalização clínica e aciona a efetivação definitiva da liquidação (captura de reserva no cartão ou consolidação de guia de faturamento).
- **RF-09: Parametrizar Políticas Operacionais da Unidade**: O Administrador configura metas de tempo de espera (SLA) por nível de gravidade, tempo médio de atendimento (TMA), fator de segurança de backpressure ($\alpha$), cotas diárias e ativação de perfis operacionais da unidade.
- **RF-10: Disponibilizar Telemetria e Auditoria de Capacidade**: O sistema calcula e disponibiliza continuamente os indicadores operacionais da unidade (TME, TMA, taxa de cumprimento de SLA, taxa de ocupação médica, desistências e no-shows), emitindo alertas visuais preventivos quando o SLA estiver em risco e fornecendo trilha auditável de eventos.

---

## 5. Regras de Negócio e Invariantes (Design by Contract)

As Regras de Negócio representam condições de integridade formal e invariantes contratuais que o software deve garantir em todos os seus ciclos operacionais:

### RN01 — Priorização Dinâmica por Gravidade Clínica
- **Categorias Padrão**: Nível 1 (Emergência/Crítico), Nível 2 (Muito Urgente), Nível 3 (Urgente), Nível 4 (Pouco Urgente) e Nível 5 (Não Urgente).
- **Invariante de Ordenação**: Dentro do mesmo nível de prioridade clínica, a ordem de atendimento segue rigorosamente a cronologia de entrada (FIFO). Um paciente de cor/nível mais urgente (ex.: Nível 2) jamais poderá ser ultrapassado por um paciente de nível menos urgente (ex.: Nível 4).

### RN02 — Bloqueio Estrito de Sobreposição e Prevenção de Deadlock (Ring Timeout)
- **Invariante 1 (Profissional)**: Um médico plantonista só pode possuir exatamente 1 (uma) consulta com status `EM_ANDAMENTO` por vez.
- **Invariante 2 (Paciente)**: Um paciente jamais pode estar vinculado a mais de 1 (um) médico simultaneamente.
- **Invariante 3 (Tolerância de Chamada / No-Show)**: Ao acionar a chamada do paciente, o sistema concede janela de tolerância de exatamente 45 segundos (ring timeout). Caso o paciente não estabeleça a conexão de áudio/vídeo nesse período, o atendimento transiciona para `PACIENTE_AUSENTE` e o médico é liberado imediatamente para nova chamada, impedindo bloqueio indefinido de tela.

### RN03 — Transição de Elegibilidade, Transparência de Fila e Chamada Segura
- **Ciclo de Estados**: O atendimento percorre estritamente o fluxo:  
  $$\text{TRIADO\_AGUARDANDO\_ELEGIBILIDADE} \longrightarrow \text{APTO\_PARA\_CHAMADA} \longrightarrow \text{CHAMANDO\_PACIENTE} \longrightarrow \text{EM\_ANDAMENTO}$$
- **Invariante de Início**: Nenhuma consulta médica pode transicionar para `EM_ANDAMENTO` sem status `APTO_PARA_CHAMADA` prévio.
- **Regra de Desvio Temporário**: Se o médico chamar o próximo e o primeiro paciente da fila por risco ainda estiver em validação assíncrona, o sistema convoca o próximo paciente já validado (`APTO_PARA_CHAMADA`). O painel do médico deve sinalizar discretamente a existência de paciente de maior prioridade em fase de validação.

### RN04 — Redirecionamento Mandatório e Salvaguarda de Deterioração Clínica (SAMU 192)
- **Invariante de Emergência Inicial**: Pacientes cujas respostas na triagem inicial revelem sinais clínicos de Nível 1 (Risco de Vida) são bloqueados de ingressar no PA Virtual. O sistema dispara alerta audiovisual de emergência, gera log de auditoria e instrui ligação imediata para o SAMU 192 ou pronto-socorro físico.
- **Invariante de Deterioração na Fila**: O acionamento da salvaguarda 'Sentiu piora nos sintomas?' com detecção de novos sinais de perigo crítico bloqueia o fluxo de teleconsulta imediatamente, orienta acionamento pré-hospitalar (192) e emite sinalização de alta prioridade na central de monitoramento da unidade.

### RN05 — Controle de Admissão, Fator de Segurança $\alpha$ e Notificação de Transbordo
- **Invariante de Admissão**: O acolhimento de novos pacientes na fila virtual é suspenso automaticamente quando satisfeita qualquer das condições:
  - **Condição A**:
    $$\text{Total de Admissões Concluídas no Dia} \ge \text{Cota Diária Máxima}$$
  - **Condição B**:
    $$\frac{\text{Pacientes Aguardando} \times \text{TMA Estimado} \times \alpha}{\text{Médicos Ativos no Turno}} > \text{Tempo Restante de Plantão}$$
    Onde $\alpha$ é o fator de margem de segurança operacional (padrão institucional: $1{,}20 \le \alpha \le 1{,}30$).
- **Invariante de Transbordo**: Pacientes já admitidos na fila antes do disparo de bloqueio mantêm o direito ao atendimento. Caso ocorra contingência crítica de escala, o sistema dispara evento de transbordo (`QUEUE_OVERFLOW_TRANSIT`) para integração com centrais de regulação externa ou aviso via canais de mensageria.

### RN06 — Preservação Soberana do Ato Médico (Sem Desconexão Forçada)
- **Invariante Clínica**: Atingir ou ultrapassar o TMA configurado aciona unicamente sinalizadores visuais discretos no prontuário do médico. É expressamente vedado ao software encerrar, bloquear ou desconectar chamadas de teleatendimento por critério de tempo transcorrido.

### RN07 — Imutabilidade, Hash de Consentimento e Precisão Temporal dos Registros
- **Invariante de Auditoria**: Toda transição de estado no ciclo de atendimento deve ser registrada em formato imutável (append-only) com carimbo de data/hora universal (UTC). O registro deve conter o hash criptográfico do TCLE aceito pelo paciente, vinculando formalmente o consentimento da teleconsulta ao histórico oficial.

---

## 6. Requisitos Não Funcionais (FURPS+ / ISO 25010) e Restrições de Sistema

Os Requisitos Não Funcionais concentram os atributos mensuráveis de qualidade, desempenho, segurança da informação, acessibilidade inclusiva e restrições arquiteturais da plataforma.

| ID | Categoria | Critério Mensurável (Nível de Serviço) | Método de Homologação / Teste |
| :--- | :--- | :--- | :--- |
| **RNF-01** | Desempenho de Fila | Reordenação dinâmica da fila e obtenção de trava atômica de alocação de atendimento em tempo $\le 200\text{ ms}$ sob carga nominal. | Testes de estresse automatizados simulando concorrência intensa de requisições de alocação. |
| **RNF-02** | Resiliência e Tolerância | Worker de validação assíncrona com recuo exponencial e timeout de contingência operacional fixado em 15 segundos. | Chaos testing e simulação de latência de rede em adaptadores de autorização externa. |
| **RNF-03** | Confiabilidade & Disponibilidade | Disponibilidade operacional da aplicação de no mínimo 99,9% em operação contínua (24/7). | Monitoramento de saúde com checagens sintéticas a cada 30 segundos e relatórios de uptime. |
| **RNF-04** | Comunicação em Tempo Real | Transmissão WebRTC (Opus / VP8 / H.264) com latência de transporte $\le 150\text{ ms}$ sob canais criptografados (SRTP). | Medição de métricas WebRTC `getStats` sob simulação de oscilações em conexões 4G/5G. |
| **RNF-05** | Segurança & LGPD | Criptografia TLS 1.3 em trânsito e AES-256 em repouso. Segregação lógica de prontuários. Trilhas de auditoria append-only imutáveis. | Auditorias automatizadas SAST/DAST no pipeline CI/CD e testes periódicos de penetração (pentest). |
| **RNF-06** | Assinatura Digital Desacoplada | Suporte à emissão de receitas e atestados com assinatura digital em nuvem no padrão ICP-Brasil via OAuth2/PKI. | Validação dos arquivos PDF gerados no verificador de conformidade de documentos do ITI. |
| **RNF-07** | Acessibilidade Digital & Usabilidade | Conformidade estrita com as diretrizes WCAG 2.1 Nível AA: contraste mínimo de 4,5:1, alvos de toque $\ge 48\times 48\text{ dp}$ e suporte a leitores de tela. | Validação automatizada via Axe/Lighthouse (score $\ge 95$) e testes manuais com leitores de tela. |
| **RNF-08** | Orquestração & Portabilidade | Manifesto declarativo de orquestração de contêineres viabilizando inicialização de ambiente limpo em menos de 10 minutos. | Execução automatizada de rotinas de provisionamento, migração e inicialização em CI/CD. |
| **RNF-09** | Arquitetura Modular & Adaptadores | Núcleo de negócio com modelos ricos e serviços desacoplados de provedores externos voláteis via adaptadores, com suporte a webhooks. | Inspeção estática de dependências e testes de integração com adaptadores mock. |
| **RNF-10** | Desempenho da Telemetria | Consolidação e atualização dos indicadores do painel operacional com defasagem temporal inferior a 5 segundos. | Medição de latência entre a emissão do evento operacional e a renderização nos dashboards. |

---

## 7. Requisitos de Transição e Governança Open Source

- **RT-01 (Perfis de Deploy e Modo SUS como No-Op)**: Disponibilização de arquivo unificado (`.env.example`) com perfis pré-configurados: no perfil `MODO_PUBLICO_SUS`, a etapa de validação financeira opera como uma instrução vazia (no-op), transicionando o paciente imediatamente de TRIADO para `APTO_PARA_CHAMADA` utilizando apenas CPF ou Cartão Nacional de Saúde (CNS), barateando o custo operacional de municípios.
- **RT-02 (Carga de Tabelas Clínicas e Procedimentos)**: Rotinas automatizadas de migração de dados contendo tabelas públicas de terminologias em saúde (classificação de diagnósticos e terminologias de atenção básica ambulatorial).
- **RT-03 (Documentação sob o Padrão Diátaxis)**: Repositório organizado estritamente segundo os quatro quadrantes do framework Diátaxis: Tutoriais (passo a passo para implantação), Guias Como-Fazer (configuração de webhooks e conectores), Referência Técnica (APIs e schemas) e Explicações (teoria de filas, fator $\alpha$ e invariantes).

---

## 8. Matriz de Rastreabilidade Vertical

A Matriz de Rastreabilidade Vertical estabelece o vínculo auditável 1:1 entre as Necessidades declaradas pelas personas, os Requisitos Funcionais, as Regras de Negócio e os Requisitos Não Funcionais:

| Necessidade (NEC) | Requisito de Negócio | Requisito Funcional (RF) | Regra de Negócio (RN) | Requisito Técnico (RNF/RT) |
| :--- | :--- | :--- | :--- | :--- |
| **NEC-01 (Acolhimento Ágil)** | Entrada em fila $< 45\text{ s}$ | RF-01 (Triagem e TCLE) | RN01 (FIFO) & RN07 (TCLE Hash) | RNF-05 (LGPD) & RNF-01 (Fila) |
| **NEC-02 (SLA e Segurança)** | Atendimento no alvo + escape | RF-03 (Alocação) & RF-06 (Escape) | RN01 (Prioridade) & RN04 (Deterioração) | RNF-01 (Performance Fila) |
| **NEC-03 (Acessibilidade)** | Usabilidade inclusiva | RF-01 (Acolhimento) & RF-06 | RN04 (Botão de Piora Acessível) | RNF-07 (WCAG 2.1 Nível AA) |
| **NEC-04 (Anti-Deadlock)** | Zero overbooking / no-show | RF-03 (Chamada e Ring Timeout) | RN02 (Ring Timeout 45s / No-Show) | RNF-01 (Locks Concorrentes) |
| **NEC-05 (PEP e Autonomia)** | Autonomia CFM nº 2.314 | RF-07 (Consulta, PEP e Assinatura) | RN06 (Sem Desconexão por Tempo) | RNF-04 (WebRTC) & RNF-06 (ICP) |
| **NEC-06 (Elegibilidade)** | Glosas $< 0{,}5\%$ sem paywall | RF-02 (Worker) & RF-05 (Exceção) | RN03 (Invariante de Elegibilidade) | RNF-02 (Timeout 15s) & RNF-09 |
| **NEC-07 (Configuração)** | Adoção adaptável aberta | RF-04 (Backpressure) & RF-09 | RN05 (Fator $\alpha$) & Transbordo | RNF-08 (Orquestração) & RT-01 |
| **NEC-08 (Governança)** | Gestão baseada em dados | RF-10 (Telemetria Operacional) | RN07 (Timestamps Imutáveis UTC) | RNF-10 (Latência Telemetria $< 5\text{ s}$) |

---

## 9. Checklist de Conformidade da Especificação (Vazquez & Simões)

- [x] **Orientada ao Domínio do Negócio**: Centrada nas necessidades do paciente, corpo clínico e gestão de saúde, sem viciar prematuramente decisões de implementação nos requisitos funcionais.
- [x] **Desacoplada Tecnologicamente**: Tecnologias de bancos de dados, brokers de mensageria e bibliotecas de vídeo situadas estritamente nos requisitos não funcionais e restrições de arquitetura.
- [x] **Jurídica e Eticamente Blindada**: Total conformidade com o CFM nº 2.314/2022, coleta auditável de TCLE sob o Art. 11 da LGPD e isenção de copyrights de protocolos fechados de triagem.
- [x] **Clínica e Operacionalmente Segura**: Salvaguarda de deterioração de sintomas na fila, tolerância de chamada contra deadlocks (ring timeout de 45 s), backpressure com margem estocástica ($\alpha$) e acessibilidade universal WCAG 2.1 AA.
- [x] **Integralmente Rastreável e Verificável**: Mapeamento bidirecional rigoroso na Matriz de Rastreabilidade Vertical e critérios de aceitação mensuráveis e testáveis para todos os requisitos de qualidade.

---
*Documento sob Licença Aberta (MIT / Apache 2.0) — Vazquez & Simões / CFM 2.314/2022*
