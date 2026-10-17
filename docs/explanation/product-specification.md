# Especificação de Requisitos de Produto e Invariantes de Domínio

## MediSync Express — Infraestrutura de Código Aberto para Pronto-Atendimento Virtual em Larga Escala (UPA Digital Nacional 24/7)

| Metadado | Detalhamento |
| :--- | :--- |
| **Referencial Metodológico** | Engenharia de Requisitos — Software Orientado ao Negócio (Vazquez & Simões) |
| **Marco Regulatório & Ético** | Resoluções CFM nº 2.314/2022 e 1.821/2007 \| LGPD (Art. 11) \| Portaria SVS/MS nº 344/98 |
| **Padrões de Acessibilidade** | Diretrizes de Acessibilidade para Conteúdo Web (WCAG 2.1 Nível AA) |
| **Status do Documento** | Aprovado (Linha de Base de Especificação Funcional) |

---

## 1. Restrições Regulatórias, Éticas e Premissas de Domínio

As restrições abaixo delimitam as fronteiras legais e deontológicas do sistema, vinculando o comportamento de todos os fluxos da aplicação.

### 1.1 Restrições Regulatórias e de Negócio

* **RN-REG-01 (Conformidade CFM nº 2.314/2022 e Respeito ao Ato Médico)**: A classificação de risco e a triagem automatizada possuem caráter estritamente orientativo e de apoio à decisão clínica. O médico assistente possui soberania diagnóstica e terapêutica inalienável e irrevogável para ratificar ou alterar a classificação ao assumir o atendimento. É expressamente vedado que a plataforma encerre, bloqueie ou force a desconexão de teleconsultas por critério temporal ou tempo de atendimento estipulado.
* **RN-REG-02 (Privacidade, LGPD Art. 11, Identificação CFM e TCLE Obrigatório)**: Tratando-se de tratamento de dados sensíveis de saúde, o ingresso na esteira do pronto-atendimento virtual exige a coleta prévia e inequívoca do Termo de Consentimento Livre e Esclarecido (TCLE) com controle criptográfico imutável. Em conformidade com as Resoluções CFM nº 1.821/2007 e 2.314/2022, o Prontuário Eletrônico do Paciente (PEP) deve conter obrigatoriamente:
  1. Identificação civil completa (Nome completo, nome social se houver, sexo biológico e data de nascimento);
  2. Nome da mãe (chave indispensável para desambiguação perante CADSUS e Receita Federal);
  3. Endereço completo com CEP (informação mandatória para eventual envio de socorro móvel de emergência via SAMU 192 e dispensação farmacêutica).
  Em atendimentos pediátricos ou de incapazes civis, o responsável legal é formalmente qualificado e outorga o consentimento do TCLE em nome do paciente.
* **RN-REG-03 (Neutralidade e Abertura de Protocolos Clínicos)**: O software é desvinculado de protocolos proprietários sujeitos a licenças restritivas ou cobrança de royalties (como o Manchester Triage System). A categorização de gravidade adota taxonomia aberta neutra e parametrizável em níveis e cores, permitindo a adoção do Acolhimento com Classificação de Risco (ACR) do SUS ou matrizes institucionais personalizadas.
* **RN-NEG-01 (Fluxo Financeiro Não Obstrutivo)**: O acolhimento e a inserção na esteira de triagem ocorrem sem bloqueios financeiros na tela inicial. A validação de cobertura do convênio ou garantia particular ocorre em segundo plano enquanto o paciente aguarda na fila. Contudo, a transição para a sala ativa de teleconsulta é estritamente condicionada à confirmação prévia de elegibilidade ou ao deferimento de contingência assistencial.
* **RN-NEG-02 (Licenciamento Open Source Permissivo)**: O núcleo funcional do MediSync Express é distribuído sob licença permissiva aprovada pela OSI (MIT ou Apache 2.0), projetado para permitir o desacoplamento de conectores de faturamento e mensageria.

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

### RN02 — Bloqueio Estrito de Sobreposição e Resolução Determinística de No-Show
* **Invariante do Profissional**: Um médico plantonista só pode possuir exatamente 1 (uma) teleconsulta com status `EM_ATENDIMENTO` por vez.
* **Invariante do Paciente**: Um paciente jamais pode estar vinculado a mais de 1 (um) médico simultaneamente.
* **Invariante de Resolução de Chamada (Ring Timeout / No-Show)**: Ao ser convocado pelo médico, o sistema reserva mutuamente as partes e concede uma janela de tolerância de 45 segundos para que o paciente confirme presença e ingresse na sala de videoconferência:
  1. O ingresso na teleconsulta transiciona o atendimento para `EM_ATENDIMENTO` e neutraliza a contagem regressiva de ausência;
  2. Caso decorram os 45 segundos sem que o paciente ingresse na sala de vídeo, o atendimento transiciona deterministicamente para `PACIENTE_AUSENTE`, os locks de reserva são liberados e o médico fica imediatamente disponível para convocar o próximo paciente.

### RN03 — Transição de Elegibilidade, Fila de Aptos e Chamada Segura
* **Ciclo de Estados Contratual**: O atendimento percorre estritamente a seguinte máquina de estados:
  $$\text{TRIADO\_AGUARDANDO\_ELEGIBILIDADE} \longrightarrow \text{APTO\_PARA\_CHAMADA} \longrightarrow \text{CHAMANDO\_PACIENTE} \longrightarrow \text{EM\_ATENDIMENTO}$$
* **Invariante de Início Clínico**: Nenhuma consulta médica pode transicionar para o status `EM_ATENDIMENTO` sem que o atendimento tenha alcançado previamente o status `APTO_PARA_CHAMADA`.
* **Regra de Desvio Temporário**: Caso o médico solicite o próximo paciente e o primeiro colocado na fila clínica ainda se encontre no estado `TRIADO_AGUARDANDO_ELEGIBILIDADE`, o sistema convoca o próximo paciente que já esteja validado (`APTO_PARA_CHAMADA`). O painel médico deve sinalizar com clareza a existência de paciente de maior prioridade em fase de validação.

### RN04 — Redirecionamento Mandatório e Salvaguarda de Deterioração Clínica (SAMU 192)
* **Invariante de Emergência Inicial**: Pacientes cujas respostas na triagem inicial revelem sinais clínicos de Nível 1 (Risco Iminente de Morte ou Instabilidade Grave) são impedidos de ingressar na fila do PA Virtual. O sistema emite alerta audiovisual imediato, registra log de auditoria e exibe instruções expressas para acionamento do SAMU 192 ou deslocamento a um serviço pré-hospitalar fixo.
* **Invariante de Deterioração na Fila**: O acionamento da salvaguarda de piora na interface de espera com confirmação de novos sinais de alarme interrompe imediatamente o fluxo virtual, instrui contato com o 192 e emite sinalização visual de alta prioridade na central de regulação da unidade.

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
* **Invariante de Auditoria**: Toda transição de estado na jornada assistencial deve ser registrada em formato imutável contendo carimbo universal de data e hora (UTC).
* **Vinculação Criptográfica do TCLE**: O registro de acolhimento deve conter o hash criptográfico do texto do TCLE apresentado e aceito pelo paciente, vinculando formal e irretratavelmente o consentimento ao prontuário clínico gerado.

---

## 3. Requisitos Funcionais (Nível de Objetivo do Usuário)

Os requisitos funcionais descrevem o comportamento observável da solução a partir das necessidades dos atores envolvidos, sem vazamento de detalhes de implementação interna:

### RF-01: Acolhimento, Triagem Estruturada e TCLE Digital (Cadastro Progressivo - Fase 1)
* **Ator**: Paciente ou Responsável Familiar.
* **Comportamento**: O usuário declara se o atendimento é próprio ou para dependente legal, preenche identificadores iniciais (CPF, data de nascimento e telefone celular), queixa principal, tempo de evolução, escala de dor e sintomas pré-definidos. Antes da submissão, concede aceite explícito ao TCLE e à política de privacidade. O sistema avalia a prioridade clínica preliminar (ACR), gera a comprovação criptográfica do termo aceito em UTC e admite o atendimento na fila com status inicial `TRIADO_AGUARDANDO_ELEGIBILIDADE`.
* **Reconexão e Autenticação Passwordless**: Pacientes que retornam à unidade ou necessitam reconectar sua sessão autenticam-se via comprovação de posse do número de telefone com código OTP de 6 dígitos, estabelecendo sessão segura com papel `PACIENTE` sem exigência de senhas alfanuméricas na urgência.

### RF-02: Validação Concorrente de Elegibilidade e Enriquecimento Cadastral (Cadastro Progressivo - Fase 2)
* **Atores**: Sistema (Rotina em Segundo Plano) e Paciente.
* **Comportamento**: Em paralelo à permanência do paciente na fila, rotinas assíncronas consultam a operadora de saúde para autorização de cobertura ou executam isenção imediata caso a instância esteja operando em perfil público SUS. Simultaneamente, a interface convida o paciente a completar os dados mandatórios do CFM (nome da mãe, sexo biológico, endereço completo com CEP, alergias medicamentosas e nome social conforme Resolução CFM nº 1.821/2007). Confirmadas a cobertura e o preenchimento regulatório, o atendimento transiciona para `APTO_PARA_CHAMADA`.

### RF-03: Convocação, Ingresso na Teleconsulta e Resolução de No-Show
* **Atores**: Médico Plantonista e Paciente.
* **Comportamento**: Ao acionar a convocação do próximo paciente, o sistema aloca com exclusividade o atendimento apto de maior prioridade clínica e maior tempo de espera, notificando imediatamente o paciente em tempo real e iniciando uma janela de tolerância de 45 segundos para resposta. O paciente acompanha sua estimativa de espera e, ao ser convocado, aciona o ingresso na sala de videoconferência. O ingresso efetivo na sala de teleconsulta transiciona o status para `EM_ATENDIMENTO` e neutraliza a contagem regressiva de ausência. Caso decorram os 45 segundos sem que o paciente ingresse na sala, o sistema transiciona deterministicamente o atendimento para `PACIENTE_AUSENTE`, libera os locks de reserva e disponibiliza o médico para chamar o próximo paciente. O paciente pode também registrar desistência voluntária antes da convocação.

### RF-04: Gerenciamento da Fila Dinâmica e Controle de Admissão (Backpressure)
* **Ator**: Sistema.
* **Comportamento**: O sistema recalcula continuamente o tempo estimado de espera com base na fila atual, no TMA e no fator de segurança $\alpha$. Se os limites de segurança da escala médica ou a cota diária forem ultrapassados, novas admissões são suspensas preventivamente com mensagem empática e orientações sobre canais alternativos de atendimento pré-hospitalar, emitindo o evento de saturação operacional `QUEUE_OVERFLOW_TRANSIT`.

### RF-05: Tratamento de Exceções e Falhas de Elegibilidade na Fila
* **Atores**: Paciente e Equipe de Regulação.
* **Comportamento**: Ocorrendo rejeição de convênio ou indisponibilidade de comunicação externa, o paciente é alertado em sua tela de espera para regularizar a documentação ou optar por contingência assistencial. O sistema preserva rigorosamente a posição cronológica e clínica conquistada na triagem inicial enquanto o paciente ajusta as pendências, promovendo-o a apto assim que a cobertura for regularizada.

### RF-06: Monitoramento de Deterioração Clínica na Fila (Escape SAMU 192)
* **Atores**: Paciente e Gestor Operacional.
* **Comportamento**: A interface de espera exibe em destaque a opção de relato de piora dos sintomas. Se acionada, uma reavaliação clínica rápida de novos sinais de risco é executada. Identificada emergência crítica (Nível 1 Vermelho), a teleconsulta é bloqueada, a orientação para ligação imediata ao SAMU 192 é apresentada e um alerta prioritário é emitido no painel da unidade. Caso não seja emergência máxima, a prioridade clínica é atualizada e a posição do paciente na fila é recalculada imediatamente.

### RF-07: Condução da Teleconsulta, Registro PEP e Prescrição Digital ICP-Brasil
* **Ator**: Médico Plantonista.
* **Comportamento**: O médico conduz a videoconferência com transmissão criptografada de áudio e vídeo, visualiza a pré-anamnese e histórico clínico, preenche a evolução clínica estruturada no padrão SOAP com diagnóstico CID-10 e emite prescrições, atestados e pedidos de exames. A emissão de medicamentos valida salvaguardas farmacêuticas legais (bloqueio de substâncias de Notificação A e B e geração automática de 2 vias para antimicrobianos), gerando documentos no formato PDF/A-1b assinados digitalmente com certificado padrão ICP-Brasil contendo QR Code do ITI para validação pública.

### RF-08: Conclusão Clínica e Fechamento Contábil pós-consulta
* **Atores**: Médico Plantonista e Sistema.
* **Comportamento**: Ao salvar o atendimento no PEP e assinar digitalmente as prescrições, o médico comanda a conclusão formal do atendimento. O sistema encerra a sessão clínica, torna o prontuário imutável, disponibiliza os documentos assinados ao paciente e aciona automaticamente a rotina de fechamento contábil e liquidação:
  1. No perfil público SUS: consolidação automática do procedimento no lote de produção ambulatorial da unidade (BPA/APAC);
  2. No perfil privado/suplementar: captura da reserva financeira de pagamento ou consolidação de guia de faturamento TISS sem risco de glosas.

### RF-09: Parametrização Dinâmica de Políticas Operacionais
* **Ator**: Diretor Clínico e Gestor de Operações.
* **Comportamento**: Permite configurar e ajustar dinamicamente os parâmetros operacionais da unidade: metas de SLA de espera por nível de risco ACR, meta de Tempo Médio de Atendimento (TMA), margem estocástica de segurança operacional ($\alpha \in [1{,}20; 1{,}30]$), cotas diárias máximas de admissão por turno e perfil de operação da unidade (Público SUS vs. Suplementar Privado).

### RF-10: Telemetria Operacional, Governança e Auditoria de Capacidade
* **Ator**: Diretor Clínico e Gestor de Operações.
* **Comportamento**: Disponibiliza painel em tempo real com indicadores operacionais e clínicos consolidados: Tempo Médio de Espera (TME) geral e estratificado pelos 5 níveis de triagem, TMA real geral e detalhado por médico plantonista, percentual de cumprimento de SLA assistencial ($\ge 95\%$), taxas de desistência voluntária e de ausência (*no-show*), mantendo trilha de auditoria imutável de todos os eventos com carimbo de tempo UTC.

---

## 4. Requisitos de Transição e Implantação

* **RT-01 (Perfis Operacionais de Implantação Dedicada)**: Suporte a arquivos declarativos de configuração provisionando a plataforma sob o perfil operacional adequado: perfil público SUS (com isenção de paywall e alimentação de lotes BPA/APAC) ou perfil privado (com validação de carteira de convênio e faturamento TISS).
* **RT-02 (Carga de Terminologias em Saúde)**: Rotinas automatizadas de inicialização de dados contendo tabelas abertas de terminologias clínicas (taxonomia ACR, CID-10 e tabela de procedimentos ambulatoriais).
* **RT-03 (Documentação Orientada ao Padrão Diátaxis)**: Repositório organizado segundo as quatro dimensões de documentação técnica: Tutoriais de implantação, Guias de como fazer, Referência técnica de contratos e Explicações conceituais de filas e regras de negócio.

---

## 5. Matriz de Rastreabilidade Vertical

A matriz abaixo estabelece a relação auditável ponta a ponta entre as Necessidades de Negócio (declaradas pelas personas no `business-vision.md`), os Requisitos Funcionais, as Regras de Domínio e os Critérios Técnicos de Qualidade:

| Necessidade de Negócio (NEC) | Requisito de Negócio | Requisito Funcional (RF) | Regra de Domínio / Invariante (RN) | Requisito Técnico (RNF/RT) |
| :--- | :--- | :--- | :--- | :--- |
| **NEC-01 (Acolhimento Ágil)** | Entrada em fila em $< 45\text{ s}$ com TCLE | RF-01 (Acolhimento, Triagem e TCLE) | RN01 (FIFO) & RN07 (Hash TCLE) | RNF-05 (LGPD) & RNF-01 (Fila) |
| **NEC-02 (SLA e Segurança)** | Atendimento no SLA com rota de fuga | RF-03 (Convocação) & RF-06 (Escape Piora) | RN01 (Priorização) & RN04 (SAMU 192) | RNF-01 (Performance) & RNF-10 |
| **NEC-03 (Acessibilidade)** | Navegação inclusiva em dispositivos móveis | RF-01 (Acolhimento) & RF-06 (Escape Piora) | RN04 (Acessibilidade do Botão de Piora) | RNF-07 (WCAG 2.1 Nível AA) |
| **NEC-04 (Anti-Deadlock)** | Zero *overbooking* e resolução de *no-show* | RF-03 (Convocação, Ingresso e No-Show) | RN02 (Ring Timeout 45s / No-Show) | RNF-01 (Atomicidade de Lock) |
| **NEC-05 (PEP e Autonomia)** | Soberania médica CFM nº 2.314/2022 | RF-07 (Consulta, PEP e Prescrição) | RN06 (Sem Desconexão por Tempo) | RNF-04 (WebRTC) & RNF-06 (ICP) |
| **NEC-06 (Validação e Faturamento)** | Glosas $< 0{,}5\%$ e liquidação sem paywall inicial | RF-02 (Elegibilidade), RF-05 (Exceção) & RF-08 (Fechamento Contábil) | RN03 (Invariante de Elegibilidade) & RN-NEG-01 | RNF-02 (Resiliência) & RNF-09 |
| **NEC-07 (Configuração)** | Parametrização dinâmica e alternância de perfis | RF-04 (Backpressure) & RF-09 (Políticas Operacionais) | RN05 (Fator $\alpha$ e Transbordo) | RNF-08 (Orquestração) & RT-01 |
| **NEC-08 (Governança)** | Decisões baseadas em métricas e auditoria | RF-10 (Telemetria Operacional e SLA) | RN07 (Auditoria Append-Only UTC) | RNF-10 (Latência Telemetria $< 5\text{ s}$) |

---

## 6. Checklist de Conformidade da Especificação (Vazquez & Simões)

- [x] **Orientada ao Domínio do Negócio**: Centrada nos direitos do paciente, no respeito ao ato médico e na sustentabilidade da unidade de pronto-atendimento, sem viciar prematuramente decisões de implementação técnica.
- [x] **Desacoplada Tecnologicamente**: Detalhes de drivers de banco, servidores de mensageria e frameworks de interface isolados na camada de arquitetura e requisitos de qualidade.
- [x] **Jurídica e Eticamente Blindada**: Integral conformidade com o CFM nº 2.314/2022 e 1.821/2007, LGPD Art. 11 (Termo de Consentimento rastreável por hash) e isenção de royalties de protocolos comerciais fechados.
- [x] **Clínica e Operacionalmente Segura**: Salvaguarda de deterioração clínica na fila com rota SAMU 192, prevenção de deadlocks operacionais com ring timeout de 45 segundos e controle de admissão por backpressure estocástico ($\alpha$).
- [x] **Integralmente Rastreável e Verificável**: Mapeamento bidirecional consistente na Matriz de Rastreabilidade Vertical com critérios mensuráveis de aceitação.
