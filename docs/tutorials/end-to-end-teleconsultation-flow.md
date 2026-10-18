# End-to-end teleconsultation flow

> Jornada clínica completa: do acolhimento e triagem Manchester à emissão e assinatura digital ICP-Brasil.

## Contexto

O Pronto Atendimento Virtual (PA Virtual) do MediSync Express opera um ciclo assistencial crítico que conecta múltiplos domínios de negócio sob requisitos rigorosos de disponibilidade, governança clínica e conformidade legal (Resoluções CFM nº 2.314/2022 e CFM nº 2.299/2021, além da LGPD). Quando um paciente busca socorro na plataforma, sua sessão transita sequencialmente por cinco fronteiras modulares independentes: acolhimento e classificação de risco, admissão com elegibilidade em fila, alocação médica sem concorrência destrutiva, teleconsulta com prontuário estruturado e emissão documental com assinatura digital em nuvem.

Este tutorial adota a metodologia Diátaxis orientada ao aprendizado prático: guiamos o desenvolvedor passo a passo pela simulação e inspeção de cada transição de estado da jornada clínica completa. Você aprenderá como os módulos colaboram por meio de eventos, comandos e portas abstratas, comprovando o funcionamento fim a fim através de baterias executáveis de testes de integração.

### Pré-requisitos para simulação local

Antes de iniciar a reprodução dos passos deste tutorial:
- Garanta a infraestrutura de contêineres ativa (`just up` com PostgreSQL 17 e Valkey 8).
- Assegure o ambiente sincronizado e migrado (`just install` e `just migrate`).
- Não é necessário hardware de token criptográfico nem certificado A3 físico: o MediSync implementa o `FakeICPBrasilSigner` para validar estruturas PAdES em conformidade sem dependências externas pagas.

---

## Conceito

A jornada clínica do paciente desdobra-se em cinco etapas determinísticas, cobrindo o trajeto integral da admissão à alta médica:

### 1. Acolhimento e triagem clínica (Manchester/ACR e salvaguarda SAMU)

A porta de entrada do paciente inicia com a coleta da queixa principal, lista de sintomas, escala analógica de dor (0–10) e o aceite formal do Termo de Consentimento Livre e Esclarecido (TCLE):
- **Contrato de Entrada Anti-IDOR:** O endpoint `POST /api/v1/fila/admissao` valida a credencial do paciente (`AdmissaoPacienteAuthDep`), garantindo que o requisitante possua legitimidade sobre o `paciente_id` e a organização.
- **Validade Forense do TCLE (RN07):** A função `calcular_hash_tcle` gera o digest SHA-256 em minúsculas do texto exato aceito pelo paciente (LGPD Art. 11). Esse hash é imutável e acompanha o registro de triagem para fins de auditoria e perícia jurídica.
- **Motor Manchester/ACR:** O método `classificar_risco_clinico` mapeia os sinais clínicos em 5 níveis de gravidade assistencial (1=Emergência Vermelho até 5=Não Urgente Azul).
- **Salvaguarda SAMU 192 (RN04):** Se o paciente reportar queixas críticas de Nível 1 (como "inconsciência", "parada respiratória" ou "dor torácica irradiada"), a plataforma aciona imediatamente o `SamuEmergencyNotifierAdapter` e levanta `EmergenciaCriticaSamuError`. Nesses casos, o atendimento em telemedicina é bloqueado e nenhuma linha de atendimento é gravada no banco relacional, direcionando o socorro imediatamente ao serviço pré-hospitalar de emergência.

### 2. Admissão e enfileiramento inteligente (PostgreSQL + Valkey ZSET)

Para pacientes estáveis (Níveis 2 a 5), o caso de uso `FilaService.admitir_paciente` executa a admissão assistencial:
- **Persistência Relacional 1:1:** São gravados atomicamente no PostgreSQL os registros de `Atendimento` (status inicial `TRIADO_AGUARDANDO_ELEGIBILIDADE`) e `Triagem` associada, sob isolamento estrito de tenant (RLS).
- **Elegibilidade Assíncrona via ARQ:** O serviço agenda um job em segundo plano com chave deduplicada (`arq:job:elegibilidade:{id}`). O worker ARQ executa `validar_elegibilidade_task`, checa cobertura contratual (SUS ou operadora privada) e transiciona o atendimento para `APTO_PARA_CHAMADA`.
- **Pontuação 64-bit Canônica (RN01, ADR-002):** A função `calcular_score` computa o score único `(prioridade_clinica * 10^12) + timestamp_epoch`. O paciente é inserido no Sorted Set do Valkey na chave `fila:{org_id}:aptos`, garantindo que emergências sempre precedam urgências e que o desempate ocorra por estrita ordem de chegada (FIFO).
- **Inspeção no Valkey:** A ordenação pode ser inspecionada via comando de terminal `valkey-cli ZRANGE "fila:<org_id>:aptos" 0 -1 WITHSCORES`.

### 3. Alocação médica atômica e salvaguarda de toque (Lua 45s)

Quando um médico plantonista solicita atendimento via `POST /api/v1/fila/chamar-proximo`, o MediSync realiza o matching determinístico sem condições de corrida:
- **Script Atômico Lua (RN02, ADR-002):** O script `alocar_chamada.lua` opera dentro de uma única execução atômica no motor Valkey, manipulando simultaneamente três chaves:
  * `KEYS[1]`: O Sorted Set da fila (`fila:{org_id}:aptos`).
  * `KEYS[2]`: O lock temporário do médico (`lock:medico:{medico_id}`).
  * `KEYS[3]`: O lock temporário do atendimento (`lock:atendimento:{atendimento_id}`).
- **Códigos Determinísticos de Retorno:**
  * `1`: Alocação concluída com sucesso (locks de 45s adquiridos).
  * `0`: Médico já em atendimento ou com lock ativo pendente.
  * `-1`: Paciente indisponível ou capturado simultaneamente por outro profissional.
  * `-2`: Fila de atendimento vazia para o tenant.
- **Ring Timeout (45s):** O atendimento passa para `CHAMANDO_PACIENTE`. Um timer assíncrono é agendado no worker; se o paciente não responder ao toque em 45 segundos, o status comuta para `PACIENTE_AUSENTE`, desfazendo o lock e liberando o profissional para o próximo chamado da fila.

### 4. Teleconsulta e prontuário eletrônico (SOAP em transação única)

Com o paciente conectado à sala de vídeo WebRTC (orquestrada pelo LiveKit SFU de forma desacoplada), o médico assistente conduz a teleconsulta e preenche o Prontuário Eletrônico do Paciente (PEP):
- **Estrutura SOAP:** O médico envia a evolução clínica via `POST /api/v1/consultations/{atendimento_id}/soap`, registrando Subjetivo (anamnese), Objetivo (exame físico virtual), Avaliação (diagnóstico CID-10 principal) e Plano (conduta terapêutica).
- **Transação Única no Service (ADR-001 §6):** O método `PEPService.salvar_evolucao_soap` realiza a inserção da entidade `EvolucaoClinica` e encerra o caso de uso executando exatamente uma chamada a `await session.commit()`. O router HTTP atua como mera casca de validação sintática e delegação, sem tocar em transações de banco.
- **Controle de Acesso Clínico:** A leitura e mutação do PEP exigem a combinação de RBAC (papel `MEDICO`), isolamento de tenant via RLS e ABAC clínico (apenas o médico titular do atendimento possui acesso autorizado).

### 5. Prescrição digital e assinatura ICP-Brasil (PAdES)

Após o diagnóstico, o médico prescreve medicamentos e sela o atendimento com fé pública nacional:
- **Emissão e Bloqueio de Portaria 344/98:** Pela rota `POST /api/v1/consultations/{atendimento_id}/documents`, emitem-se receitas e atestados. O serviço valida restrições da ANVISA, impedindo medicamentos que demandem retenção de talonário físico (Listas A/B).
- **Compilação PDF/A com QR Code:** O documento é estruturado no formato PDF/A-1b para preservação histórica de longo prazo, incluindo QR Code para verificação por farmácias e pacientes. O arquivo binário é armazenado no MinIO S3 (`orgs/{org_id}/consultations/{atend_id}/documents/{doc_id}.pdf`).
- **Assinatura PAdES em Nuvem (ADR-006):** A requisição `POST .../documents/{documento_id}/sign` encaminha as credenciais do certificado médico para o Provedor de Serviços de Assinatura (PSC). Em ambiente de testes, o adaptador `FakeICPBrasilSigner` injeta um certificado X.509 de teste genuíno com envelope PAdES compatível com a biblioteca PyHanko, atualizando o hash SHA-256 do documento assinado.
- **Encerramento Imutável:** A rota `POST /api/v1/consultations/{atendimento_id}/finalize` comuta o atendimento para `CONCLUIDO`. A partir desse momento, as evoluções e receitas tornam-se juridicamente imutáveis; novas tentativas de assinatura são rejeitadas com status 403 Forbidden.

---

## Onde no código

- Impl: `src/modules/triage/domain/classification.py:classificar_risco_clinico`
- Impl: `src/modules/triage/domain/classification.py:calcular_hash_tcle`
- Impl: `src/modules/queue/presentation/routers/admissao_router.py:admitir_paciente`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService.admitir_paciente`
- Impl: `src/modules/queue/domain/scoring.py:calcular_score`
- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua:alocar_chamada`
- Impl: `src/modules/queue/presentation/routers/alocacao_router.py:chamar_proximo_paciente`
- Impl: `src/modules/consultation/presentation/routers/consultation_router.py:salvar_evolucao_soap`
- Impl: `src/modules/consultation/application/services/pep_service.py:PEPService.salvar_evolucao_soap`
- Impl: `src/modules/consultation/infrastructure/pyhanko_signer.py:FakeICPBrasilSigner`
- Impl: `src/worker/tasks/eligibility.py:validar_elegibilidade_task`
- Spec: `docs/explanation/domains/triage-domain.md`
- Spec: `docs/explanation/domains/queue-domain.md`
- Spec: `docs/explanation/domains/consultation-domain.md`
- Spec: `docs/adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Spec: `docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md`
- Prova viva: `tests/integration/test_admissao_integrada_flow.py:test_admissao_integrada_persists_both_models_and_enqueues_arq_job`
- Prova viva: `tests/integration/test_admissao_integrada_flow.py:test_admissao_integrada_emergencia_samu_dispatches_alert_and_blocks_db`
- Prova viva: `tests/integration/test_lua_scripts.py:test_alocar_chamada_adr002_scenarios`
- Prova viva: `tests/integration/test_ring_timeout_flow.py:test_alocar_chamada_schedules_arq_job_in_valkey`
- Prova viva: `tests/integration/test_pep_transaction.py:test_salvar_evolucao_soap_service_commit_visivel_outra_sessao`
- Prova viva: `tests/integration/test_pep_transaction.py:test_assinar_documento_service_commit_visivel_outra_sessao`
- Prova viva: `tests/integration/test_document_signing_endpoint.py:test_assinar_documento_clinico_pades_flow`
- Ver: `rg -n "admitir_paciente" src/modules/queue/application/services/fila_service.py`
- Ver: `rg -n "alocar_chamada" src/modules/queue/infrastructure/lua/`
- Ver: `rg -n "salvar_evolucao_soap" src/modules/consultation/application/services/pep_service.py`
- Ver: `rg -n "FakeICPBrasilSigner" src/modules/consultation/infrastructure/`
- Ver: `rg -n "validar_elegibilidade_task" src/worker/tasks/eligibility.py`

---

## Verificação

Execute a bateria de integração unificada para simular os cinco estágios da jornada clínica em infraestrutura real:

```bash
uv run pytest tests/integration/test_admissao_integrada_flow.py tests/integration/test_pep_transaction.py tests/integration/test_document_signing_endpoint.py -v
```

Cada teste atua como prova viva de uma etapa crítica da teleconsulta:

1. **Admissão e Fila (`test_admissao_integrada_flow.py`):**
   - Comprova a persistência atômica das entidades relacionais `Atendimento` e `Triagem`.
   - Verifica o agendamento do job ARQ e a promoção do atendimento para `APTO_PARA_CHAMADA`.
   - Inspeciona a presença do score 64-bit ordenado no ZSET do Valkey.

2. **Salvaguarda SAMU (`test_admissao_integrada_flow.py`):**
   - Comprova que sintomas críticos disparam o adaptador de notificação do SAMU 192.
   - Assegura que nenhuma linha de atendimento é gravada no banco relacional em casos de emergência vital.

3. **Transação Única PEP (`test_pep_transaction.py`):**
   - Verifica que o método do serviço commita a evolução SOAP de forma visível para outras sessões assíncronas do banco.
   - Valida que o encerramento da consulta altera o status do atendimento para `CONCLUIDO`.

4. **Assinatura PAdES e Imutabilidade (`test_document_signing_endpoint.py`):**
   - Emite receita médica via endpoint REST e aplica assinatura digital com `FakeICPBrasilSigner`.
   - Baixa o PDF resultante e valida a integridade da assinatura criptográfica via `pyhanko`.
   - Comprova que a tentativa de assinar novo documento após consulta finalizada é bloqueada com erro 403 Forbidden.

---

## Ver também

- [Onboarding quickstart](onboarding-quickstart.md) — preparação do ambiente local e stack Docker.
- [Backend first feature](backend-first-feature.md) — desenvolvimento de endpoints finos no Hexagonal Pragmático.
- [ADR-001: Hexagonal Pragmático](../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md) — isolamento entre camadas e ownership de transações.
- [ADR-002: Alocação Atômica com Lua](../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md) — ordenação no ZSET e locks de 45 segundos.
- [ADR-006: Assinatura Digital ICP-Brasil](../adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md) — emissão PAdES em nuvem e salvaguardas CFM.
- [Domínio de Triagem](../explanation/domains/triage-domain.md) — classificação Manchester/ACR e consentimento forense TCLE.
- [Domínio de Fila](../explanation/domains/queue-domain.md) — backpressure estocástico, score 64-bit e ciclo de atendimento.
- [Domínio de Consulta](../explanation/domains/consultation-domain.md) — governança de prontuário eletrônico PEP e documentos clínicos.
- [Executar testes](../how-to/backend/run-tests.md) — execução de suítes rápidas, unitárias e de integração.
- [Dicionário de Chaves Valkey](../reference/valkey/keys-dictionary.md) — catálogo de chaves e TTLs de locks em memória.
- [Tarefas de Worker ARQ](../reference/worker/arq-tasks.md) — catálogo de jobs assíncronos e processamento em segundo plano.
- [Documentation Standards](../reference/architecture-standards/documentation-standards.md) — padrão atômico-denso Diátaxis.
