# Especificação de Requisitos de Produto e Invariantes de Domínio

## MediSync Express — Plataforma de Código Aberto para Pronto-Atendimento Virtual (PA Digital 24/7)

| Metadado | Detalhamento |
| :--- | :--- |
| **Referencial Metodológico** | Engenharia de Requisitos — Software Orientado ao Negócio (Vazquez & Simões) |
| **Marco Regulatório & Ético** | Resolução CFM nº 2.314/2022 \| Resolução CFM nº 1.821/2007 \| LGPD (Art. 11) |
| **Padrões de Acessibilidade** | Diretrizes de Acessibilidade para Conteúdo Web (WCAG 2.1 Nível AA) |
| **Status do Documento** | Aprovado (Linha de Base de Especificação Funcional) |

---

## 1. Restrições Regulatórias, Éticas e Premissas de Domínio

As restrições abaixo delimitam as fronteiras legais e deontológicas do sistema, vinculando o comportamento de todos os fluxos da aplicação.

### 1.1 Restrições Regulatórias e de Negócio

* **RN-REG-01 (Conformidade CFM nº 2.314/2022 e Respeito ao Ato Médico)**: A classificação de risco e a triagem automatizada possuem caráter estritamente orientativo e de apoio à decisão clínica. O médico assistente possui soberania diagnóstica e terapêutica inalienável e irrevogável para ratificar ou alterar a classificação ao assumir o atendimento. É expressamente vedado que a plataforma encerre, bloqueie ou force a desconexão de teleconsultas por critério temporal ou tempo de atendimento estipulado.
* **RN-REG-02 (Privacidade, LGPD Art. 11, Identificação CFM e TCLE Obrigatório)**: Tratando-se de tratamento de dados sensíveis de saúde, o ingresso na esteira do pronto-atendimento virtual exige a coleta prévia e inequívoca do Termo de Consentimento Livre e Esclarecido (TCLE) com controle de versão criptográfico. Em conformidade com as Resoluções CFM nº 1.821/2007 e 2.314/2022, o Prontuário Eletrônico do Paciente (PEP) deve conter obrigatoriamente:
  1. Identificação civil completa (Nome completo, nome social se houver, sexo biológico e data de nascimento);
  2. Nome da mãe (chave indispensável para desambiguação perante CADSUS e Receita Federal);
  3. Endereço completo com CEP (informação mandatória para envio de socorro móvel de emergência via SAMU 192 e dispensação farmacêutica).
  Em atendimentos pediátricos ou de incapazes civis, o responsável legal é formalmente qualificado e outorga o consentimento do TCLE em nome do paciente.
* **RN-REG-03 (Neutralidade e Abertura de Protocolos Clínicos)**: O software é desvinculado de protocolos proprietários sujeitos a licenças restritivas ou cobrança de royalties (como o Manchester Triage System). A categorização de gravidade adota taxonomia neutra aberta parametrizável em níveis e cores, permitindo a adoção do Acolhimento com Classificação de Risco (ACR) do SUS ou matrizes institucionais personalizadas.
* **RN-NEG-01 (Fluxo Financeiro Não Obstrutivo)**: O acolhimento e a inserção na esteira de triagem ocorrem sem bloqueios financeiros na tela inicial. A validação de cobertura do convênio ou garantia particular ocorre em segundo plano. Contudo, a transição para a sala ativa de teleconsulta é estritamente condicionada à confirmação prévia de elegibilidade ou ao deferimento de contingência assistencial.
* **RN-NEG-02 (Licenciamento Open Source Permissivo)**: O núcleo funcional do MediSync Express é distribuído sob licença permissiva aprovada pela OSI (MIT ou Apache 2.0), projetado para permitir o desacoplamento de conectores proprietários de faturamento e mensageria.

### 1.2 Premissas de Domínio

* **PREM-01 (Infraestrutura de Mídia e WebRTC)**: A entidade mantenedora disponibiliza ambiente de sinalização e roteamento de mídia (SFU WebRTC) com suporte a canais criptografados em trânsito.
* **PREM-02 (Certificação Digital de Profissionais)**: Os médicos plantonistas dispõem de certificados digitais válidos e compatíveis com a Infraestrutura de Chaves Públicas Brasileira (ICP-Brasil), operando via nuvem (PSC) ou dispositivo criptográfico físico.
* **PREM-03 (Gestão Ativa da Capacidade Instalada)**: A instituição operadora estabelece e gerencia ativamente a escala médica e a quantidade de profissionais em plantão simultâneo, calibrando a taxa de absorção de acordo com a demanda esperada.

---

## 2. Invariantes de Domínio e Regras Contratuais (Design by Contract)

As regras de negócio abaixo constituem as condições de integridade formal e invariantes contratuais que o software deve garantir sob qualquer circunstância de execução:

### RN01 — Priorização Dinâmica por Gravidade Clínica
* **Taxonomia Padrão**: Nível 1 (Emergência/Crítico - Vermelho), Nível 2 (Muito Urgente - Laranja), Nível 3 (Urgente - Amarelo), Nível 4 (Pouco Urgente - Verde) e Nível 5 (Não Urgente - Azul).
* **Invariante de Ordenação Estrita**: Dentro de um mesmo nível de prioridade clínica, a ordem de convocação segue rigorosamente a cronologia de entrada (FIFO - *First In, First Out*).
* **Invariante de Prevalência Clínica**: Um paciente com grau de risco mais urgente (ex.: Nível 2) jamais poderá ser ultrapassado na fila de convocação por um paciente de risco inferior (ex.: Nível 3 ou 4), independentemente do tempo de espera acumulado pelo paciente menos urgente.

### RN02 — Bloqueio Estrito de Sobreposição e Prevenção de Deadlock (Ring Timeout)
* **Invariante do Profissional**: Um médico plantonista só pode possuir exatamente 1 (uma) teleconsulta com status `EM_ANDAMENTO` por vez.
* **Invariante do Paciente**: Um paciente jamais pode estar vinculado a mais de 1 (um) médico simultaneamente.
* **Invariante de Resolução de Chamada (Ring Timeout / No-Show)**: Ao disparar a chamada de um paciente, o sistema concede uma janela de tolerância de exatamente **45 segundos**. Caso o paciente não estabeleça a conexão de áudio/vídeo nesse período:
  1. O atendimento transiciona deterministicamente para o status `PACIENTE_AUSENTE`;
  2. O médico é liberado imediatamente para efetuar nova chamada, impedindo travamento de tela ou bloqueio da fila.

### RN03 — Transição de Elegibilidade, Transparência de Fila e Chamada Segura
* **Ciclo de Estados Contratual**: O atendimento percorre estritamente a seguinte máquina de estados:
  $$\text{TRIADO\_AGUARDANDO\_ELEGIBILIDADE} \longrightarrow \text{APTO\_PARA\_CHAMADA} \longrightarrow \text{CHAMANDO\_PACIENTE} \longrightarrow \text{EM\_ANDAMENTO}$$
* **Invariante de Início Clínico**: Nenhuma consulta médica pode transicionar para o status `EM_ANDAMENTO` sem que o atendimento tenha alcançado previamente o status `APTO_PARA_CHAMADA`.
* **Regra de Desvio Temporário**: Caso o médico solicite o próximo paciente e o primeiro colocado na fila clínica ainda se encontre no estado `TRIADO_AGUARDANDO_ELEGIBILIDADE`, o sistema convoca o próximo paciente que já esteja validado (`APTO_PARA_CHAMADA`). O painel médico deve sinalizar com clareza a existência de paciente de maior prioridade em fase de validação.

### RN04 — Redirecionamento Mandatório e Salvaguarda de Deterioração Clínica (SAMU 192)
* **Invariante de Emergência Inicial**: Pacientes cujas respostas na triagem inicial revelem sinais clínicos de Nível 1 (Risco Iminente de Morte ou Instabilidade Grave) são impedidos de ingressar na fila do PA Virtual. O sistema emite alerta audiovisual imediato, registra log de auditoria e exibe instruções expressas para acionamento do SAMU 192 ou deslocamento a um serviço pré-hospitalar fixo.
* **Invariante de Deterioração na Fila**: O acionamento da salvaguarda *"Sentiu piora nos sintomas?"* na interface de espera com confirmação de novos sinais de alarme interrompe imediatamente o fluxo virtual, instrui contato com o 192 e emite sinalização visual de alta prioridade na central de regulação da unidade.

### RN05 — Controle de Admissão, Fator de Segurança $\alpha$ e Notificação de Transbordo
* **Invariante de Admissão**: O acolhimento de novos pacientes na fila virtual é suspenso preventivamente quando satisfeita qualquer das seguintes condições:
  * **Condição A (Cota Absoluta Diária)**:
    $$\text{Total de Admissões Concluídas no Dia} \ge \text{Cota Diária Máxima}$$
  * **Condição B (Capacidade de Escala Restante)**:
    $$\frac{\text{Pacientes Aguardando} \times \text{TMA Estimado} \times \alpha}{\text{Médicos Ativos no Turno}} > \text{Tempo Restante de Plantão}$$
    Onde $\alpha$ representa a margem estocástica de segurança operacional ($1{,}20 \le \alpha \le 1{,}30$).
* **Invariante de Transbordo**: Pacientes já admitidos na esteira antes da suspensão de entrada têm seu atendimento assegurado. Ocorrida uma contingência crítica de escala, o sistema dispara o evento de transbordo `QUEUE_OVERFLOW_TRANSIT` para integração com centrais de regulação externa ou aviso via canais de mensageria.

### RN06 — Preservação Soberana do Ato Médico (Sem Desconexão Forçada)
* **Invariante Clínica**: Atingir ou ultrapassar o Tempo Médio de Atendimento (TMA) previsto gera unicamente sinalizadores visuais discretos no prontuário do profissional. É terminantemente proibido que o software encerre, bloqueie ou interrompa a transmissão de teleatendimento por critério de tempo decorrido.

### RN07 — Imutabilidade, Hash de Consentimento e Precisão Temporal dos Registros
* **Invariante de Auditoria**: Toda transição de estado na jornada assistencial deve ser registrada em formato imutável (*append-only*) contendo carimbo universal de data e hora (UTC).
* **Vinculação Criptográfica do TCLE**: O registro de acolhimento deve conter o hash criptográfico do texto do TCLE apresentado e aceito pelo paciente, vinculando formal e irretratavelmente o consentimento ao prontuário clínico gerado.

---

## 3. Requisitos Funcionais (Nível de Objetivo do Usuário)

Os requisitos funcionais descrevem o comportamento observável da solução a partir das necessidades dos atores envolvidos:

### RF-01: Acolhimento, Triagem Estruturada e TCLE Digital (Cadastro Progressivo - Fase 1)
* **Ator**: Paciente ou Responsável Familiar.
* **Comportamento**: O usuário declara se o atendimento é próprio ou para dependente legal, preenche identificadores iniciais (CPF, data de nascimento e telefone com validação de uso temporário), queixa principal, tempo de evolução, escala de dor e sinais de alerta pré-definidos. Antes da submissão, concede aceite explícito ao TCLE e à política de privacidade. O sistema avalia a prioridade preliminar, gera o hash do termo aceito e insere o atendimento na fila com status `TRIADO_AGUARDANDO_ELEGIBILIDADE`.

### RF-02: Validação Concorrente de Elegibilidade e Enriquecimento Cadastral (Cadastro Progressivo - Fase 2)
* **Atores**: Sistema (Worker de Segundo Plano) e Paciente.
* **Comportamento**: Em paralelo à permanência do paciente na fila, workers em background consultam a operadora de saúde para autorização de cobertura ou executam instrução nula (*no-op*) caso a instância esteja operando em perfil público SUS. Simultaneamente, a interface convida o paciente a completar os dados mandatórios do CFM (nome da mãe, sexo biológico, endereço completo com CEP e alergias medicamentosas). Confirmadas a elegibilidade e o preenchimento, o atendimento transiciona para `APTO_PARA_CHAMADA`.

### RF-03: Realização de Chamada, Habilitação de Atendimento e Tratamento de No-Show
* **Atores**: Médico Plantonista e Paciente.
* **Comportamento**: Ao clicar em *"Chamar Próximo"*, o sistema aloca o paciente no estado `APTO_PARA_CHAMADA` de maior prioridade clínica. A interface do paciente emite aviso sonoro e visual em tela cheia com contagem regressiva de 45 segundos. Caso o paciente atenda, a sala de videoconferência e o prontuário são abertos simultaneamente. Caso expire o tempo limite sem atendimento, o status muda deterministicamente para `PACIENTE_AUSENTE` e o médico é liberado imediatamente.

### RF-04: Gerenciamento da Fila Dinâmica e Controle de Admissão (Backpressure)
* **Ator**: Sistema.
* **Comportamento**: O sistema recalcula continuamente o tempo estimado de espera com base na fila atual, no TMA e no fator $\alpha$. Se os limites de segurança da escala médica ou a cota diária forem ultrapassados, novas admissões são bloqueadas preventivamente com mensagem empática e orientações sobre canais alternativos de atendimento.

### RF-05: Tratamento de Exceções e Falhas de Elegibilidade na Fila
* **Atores**: Paciente e Equipe de Regulação.
* **Comportamento**: Ocorrendo rejeição de convênio ou indisponibilidade de comunicação externa, o paciente é alertado em sua tela de espera para regularizar a documentação ou submeter novo meio de pagamento. O sistema preserva rigorosamente a posição cronológica e clínica conquistada na triagem inicial enquanto o paciente ajusta as pendências.

### RF-06: Monitoramento de Deterioração Clínica na Fila (Escape SAMU 192)
* **Atores**: Paciente e Gestor Operacional.
* **Comportamento**: A interface de espera exibe em destaque a opção *"Sentiu piora nos sintomas?"*. Se acionada, uma checagem rápida de novos sinais de risco é exibida. Identificada emergência crítica, a teleconsulta é bloqueada, a orientação para ligação imediata ao SAMU 192 é apresentada e um alerta prioritário é emitido no painel da unidade.

### RF-07: Condução da Teleconsulta, Registro PEP e Assinatura Digital ICP-Brasil
* **Ator**: Médico Plantonista.
* **Comportamento**: O médico conduz a videoconferência com transmissão criptografada de áudio e vídeo, visualiza a pré-anamnese, preenche a evolução clínica no prontuário e prescreve receitas, atestados e pedidos de exames. Ao finalizar, os documentos são assinados digitalmente via certificado padrão ICP-Brasil em nuvem (PSC OAuth2).

### RF-08: Conclusão e Liquidação de Atendimento
* **Atores**: Médico Plantonista e Sistema.
* **Comportamento**: Ao salvar o atendimento no PEP e assinar digitalmente as prescrições, o médico clica em *"Concluir Atendimento"*. O sistema registra a finalização clínica, fecha a sala de videoconferência, disponibiliza os documentos assinados ao paciente e aciona o fechamento contábil (captura de reserva financeira ou consolidação de lote de faturamento).

### RF-09: Parametrização de Políticas Operacionais da Unidade
* **Ator**: Carlos Drumond (Gestor Operacional / Administrador).
* **Comportamento**: Permite configurar metas de SLA de espera por cor/nível clínico, TMA padrão de consulta, coeficiente estocástico $\alpha$, cotas de admissão por turno e alternar entre perfis de deploy (SUS vs. Convênios/Particular).

### RF-10: Telemetria Operacional e Auditoria de Capacidade
* **Ator**: Gestor Operacional / Corpo Clínico.
* **Comportamento**: Disponibiliza painel em tempo real com métricas consolidadas: Tempo Médio de Espera (TME), TMA real vs. projetado, taxa de cumprimento de SLA, taxa de desistência/abandono de fila e índice de *no-show*, mantendo trilha de auditoria completa de eventos.

---

## 4. Requisitos de Transição e Implantação

* **RT-01 (Perfis de Configuração e Modo SUS como No-Op)**: Disponibilização de arquivo declarativo de variáveis de ambiente com perfis prontos para uso. No perfil `MODO_PUBLICO_SUS`, o adaptador de validação de elegibilidade atua como uma operação vazia (*no-op*), transicionando o paciente imediatamente para `APTO_PARA_CHAMADA` com identificação via CPF ou Cartão Nacional de Saúde (CNS).
* **RT-02 (Carga de Terminologias em Saúde)**: Rotinas automatizadas de inicialização de dados contendo tabelas abertas de terminologias clínicas (classificação de queixas e terminologia ambulatorial).
* **RT-03 (Documentação Orientada ao Padrão Diátaxis)**: Repositório organizado segundo as quatro dimensões de documentação: Tutoriais de implantação, Guias de como fazer, Referência técnica de contratos e Explicações conceituais de filas e regras de negócio.

---

## 5. Matriz de Rastreabilidade Vertical

A matriz abaixo estabelece a relação auditável ponta a ponta entre as Necessidades de Negócio (declaradas pelas personas), os Requisitos Funcionais, as Regras de Domínio e os Critérios Técnicos de Qualidade:

| Necessidade de Negócio (NEC) | Requisito de Negócio | Requisito Funcional (RF) | Regra de Domínio / Invariante (RN) | Requisito Técnico (RNF/RT) |
| :--- | :--- | :--- | :--- | :--- |
| **NEC-01 (Acolhimento Ágil)** | Entrada em fila em $< 45\text{ s}$ | RF-01 (Acolhimento, Triagem e TCLE) | RN01 (FIFO) & RN07 (Hash TCLE) | RNF-05 (LGPD) & RNF-01 (Fila) |
| **NEC-02 (SLA e Segurança)** | Atendimento no SLA com rota de fuga | RF-03 (Alocação) & RF-06 (Escape Piora) | RN01 (Priorização) & RN04 (SAMU 192) | RNF-01 (Performance) & RNF-10 |
| **NEC-03 (Acessibilidade)** | Navegação inclusiva em mobile | RF-01 (Acolhimento) & RF-06 (Escape) | RN04 (Acessibilidade do Botão de Piora) | RNF-07 (WCAG 2.1 Nível AA) |
| **NEC-04 (Anti-Deadlock)** | Zero *overbooking* e resolução de *no-show* | RF-03 (Chamada e Ring Timeout) | RN02 (Ring Timeout 45s / No-Show) | RNF-01 (Atomicidade de Lock) |
| **NEC-05 (PEP e Autonomia)** | Soberania médica CFM 2.314 | RF-07 (Consulta, PEP e Assinatura) | RN06 (Sem Desconexão por Tempo) | RNF-04 (WebRTC) & RNF-06 (ICP) |
| **NEC-06 (Elegibilidade)** | Glosas $< 0{,}5\%$ sem paywall obstrutivo | RF-02 (Worker Elegibilidade) & RF-05 (Exceção) | RN03 (Invariante de Elegibilidade) | RNF-02 (Resiliência) & RNF-09 |
| **NEC-07 (Configuração)** | Flexibilidade de deploy (SUS vs. Privado) | RF-04 (Backpressure) & RF-09 (Políticas) | RN05 (Fator $\alpha$ e Transbordo) | RNF-08 (Orquestração) & RT-01 |
| **NEC-08 (Governança)** | Decisões baseadas em métricas e auditoria | RF-10 (Telemetria Operacional) | RN07 (Auditoria Append-Only UTC) | RNF-10 (Latência Telemetria $< 5\text{ s}$) |

---

## 6. Checklist de Conformidade da Especificação (Vazquez & Simões)

- [x] **Orientada ao Domínio do Negócio**: Centrada nos direitos do paciente, no respeito ao ato médico e na sustentabilidade da unidade de pronto-atendimento, sem viciar prematuramente decisões de implementação técnica.
- [x] **Desacoplada Tecnologicamente**: Detalhes de drivers de banco, servidores de mensageria e frameworks de interface isolados na camada de arquitetura e requisitos de qualidade.
- [x] **Jurídica e Eticamente Blindada**: Integral conformidade com o CFM nº 2.314/2022 e 1.821/2007, LGPD Art. 11 (Termo de Consentimento rastreável por hash) e isenção de royalties de protocolos comerciais fechados.
- [x] **Clínica e Operacionalmente Segura**: Salvaguarda de deterioração clínica na fila com rota SAMU 192, prevenção de deadlocks operacionais com ring timeout de 45 segundos e controle de admissão por backpressure estocástico ($\alpha$).
- [x] **Integralmente Rastreável e Verificável**: Mapeamento bidirecional consistente na Matriz de Rastreabilidade Vertical com critérios mensuráveis de aceitação.
