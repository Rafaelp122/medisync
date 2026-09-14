# [ADR-010] Cadastro Progressivo em Duas Etapas e Identificação Clínica Segura

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (NEC-01, RN-REG-02, RF-01, RF-02) |

---

## 1. Contexto e Declaração do Problema

O ingresso de pacientes em um Pronto-Atendimento Virtual (PA Digital 24/7) sob demanda espontânea apresenta um conflito fundamental de engenharia e produto:
1. **Necessidade de Fricção Mínima em Urgência (< 45s - NEC-01)**: Pacientes com febre alta, dor aguda ou mal-estar não toleram formulários burocráticos extensos antes de serem acolhidos e triados clinicamente.
2. **Exigências Legais e Regulatórias Rígidas (CFM nº 1.821/2007 e 2.314/2022)**: O prontuário médico brasileiro exige compulsoriamente nome civil completo, data de nascimento, sexo biológico, nome da mãe (desambiguação no CADSUS e Receita Federal) e **endereço completo com CEP**. O endereço é vital: se o paciente sofrer uma PCR, síncope ou choque anafilático durante a teleconsulta, o médico precisa despachar a ambulância do SAMU 192 para o local exato.
3. **Cenário Pediátrico e Dependentes**: Grande parte dos atendimentos de urgência envolve crianças pequenas trazidas pelos pais. A criança não possui celular ou e-mail próprio, e o TCLE deve ser assinado pelo responsável legal.
4. **Prevenção a Fraudes e Vazamento de Dados Sensíveis (LGPD Art. 11)**: Apenas digitar "CPF e telefone" permitiria que terceiros digitassem CPFs alheios para receber SMS e acessar prontuários e históricos clínicos confidenciais de outras pessoas.

---

## 2. Drivers de Decisão

- **Tempo de Entrada em Fila**: Garantir acolhimento clínico inicial em tempo $< 45\text{ s}$.
- **Conformidade CFM / LGPD**: Prontuário médico 100% preenchido com dados legais e endereço de socorro antes da teleconsulta iniciar.
- **Segurança Farmacológica**: Coleta obrigatória de alergias medicamentosas antes de permitir a emissão de receitas.
- **Suporte Nativo a Menores/Dependentes**: Separação clara entre o Titular do acesso (responsável) e o Paciente clínico atendido.

---

## 3. Opções Consideradas

### Opção 1: Formulário Burocrático Tradicional na Primeira Tela
Exigir todos os 25 a 30 campos cadastrais (identificação, endereço, nome da mãe, RG, convênio, cartão) antes de permitir a triagem.
- *Prós*: Todos os dados já estão salvos desde o primeiro clique.
- *Contras*: Taxa de abandono superior a 40%; pacientes em estado grave demoram minutos para serem triados, ferindo o princípio de pronto-atendimento ágil.

### Opção 2: Cadastro Minimalista (Apenas CPF + Telefone)
Coletar apenas CPF e celular com código OTP.
- *Prós*: Entrada ultrarrápida.
- *Contras*: Ilegal perante o CFM; ausência de endereço em caso de resgate de emergência; ausência de histórico de alergias; vulnerabilidade de invasão de prontuários por simples digitação de CPF de terceiros; impossibilidade de atender crianças sem celular.

### Opção 3: Cadastro Progressivo em Duas Etapas (*Progressive Onboarding*)
Dividir o ciclo em dois momentos distintos:
- **Fase 1 (Fast-Track de Acolhimento e Triagem - $< 45\text{ s}$)**: Identificação primária cruzada (CPF + Data de Nascimento do paciente), declaração de titular vs. dependente, contato (Telefone + OTP), queixa clínica, sinais de alarme e aceite formal do TCLE. Ingressa imediatamente na fila dinâmica.
- **Fase 2 (Enriquecimento Cadastral e Clínico na Fila de Espera)**: Enquanto o paciente aguarda a alocação médica na fila dinâmica, a interface conduz um assistente para preenchimento de endereço com CEP (via autopreenchimento de CEP), nome da mãe, sexo biológico, histórico de alergias medicamentosas conhecidas e medicamentos de uso contínuo.
- *Prós*: Combina velocidade emergencial com conformidade legal máxima; o tempo de espera ocioso na fila é convertido em tempo produtivo de cadastro; o médico recebe o prontuário completo.
- *Contras*: Exige um estado intermediário de checagem antes de liberar o paciente para chamada médica ativa.

---

## 4. Decisão

Adotamos a **Opção 3: Cadastro Progressivo em Duas Etapas (*Progressive Onboarding*)**.

### Diretrizes de Execução:
1. **Barreira Anti-Fraude Primária**: O login e acolhimento exigem a validação combinada de `CPF` e `Data de Nascimento`. Esse cruzamento bloqueia tentativas de invasão por digitação aleatória de CPFs de terceiros.
2. **Separação Titular vs. Dependente (Acolhimento Familiar & Pediatria)**:
   - `titular_id`: Paciente adulto autenticado via celular e OTP (Responsável Legal que assina o TCLE).
   - `dependente_id`: Paciente clínico atendido (filho menor ou tutelado, vinculado na tabela `dependentes`).
   - **Suporte a Recém-Nascidos (SUS e Pediatria)**: Bebês e crianças que ainda não possuam CPF próprio são identificados pelo Cartão Nacional de Saúde (CNS) ou certidão de nascimento, com o CPF do titular servindo como âncora probatória do TCLE.
3. **Enriquecimento Concorrente**: O paciente só recebe status `APTO_PARA_CHAMADA` quando:
   - A validação de elegibilidade estiver confirmada (ou em perfil SUS).
   - O endereço com CEP e o questionário de alergias medicamentosas estiverem preenchidos.
4. **Desvio de Emergência na Fase 1**: Se a triagem inicial acusar Nível 1 (Risco de Vida), o sistema redireciona imediatamente para o SAMU 192, sem exigir qualquer preenchimento adicional da Fase 2.

---

## 5. Consequências

### Positivas:
- **Zero Abandono**: Paciente acolhido e com prioridade clínica assegurada na fila em menos de 45 segundos.
- **Segurança no Ato Médico**: O médico abre o PEP com endereço completo de socorro na tela e aviso visual em destaque de alergias (ex.: alergia a penicilinas/dipirona).
- **Atendimento Familiar**: Pais atendem filhos menores com segurança jurídica e prontuários individualizados.

### Negativas / Riscos Mitigados:
- *Risco de o Paciente Não Completar a Fase 2 na Fila*: Mitigado por avisos interativos na tela de espera ("Complete seu endereço enquanto aguarda para liberar sua chamada"). Caso o médico chame e o paciente não tenha terminado, o sistema convoca o próximo da fila já enriquecido (regra de desvio temporário RN03).
