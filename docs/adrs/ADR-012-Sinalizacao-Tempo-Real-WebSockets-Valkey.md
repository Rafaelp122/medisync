# [ADR-012] Sinalização em Tempo Real via WebSockets e Valkey Pub/Sub

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (NEC-01, NEC-02, RF-03, RN02, RNF-10) |

---

## 1. Contexto e Declaração do Problema

A esteira de atendimento de pronto-atendimento virtual exige sincronização instantânea de estados entre pacientes, médicos e retaguarda:
1. **Posicionamento na Fila**: O paciente precisa acompanhar seu avanço na fila dinâmica em tempo real (*"Você é o 2º da fila. Tempo estimado: 7 min"*).
2. **Disparo Imediato de Chamada (Ring 45s)**: Quando o médico aloca o paciente, a interface do paciente precisa iniciar imediatamente o toque sonoro e visual da chamada. Qualquer atraso de alguns segundos consome a preciosa janela de 45 segundos do *ring timeout* (RN02).
3. **Desobstrução Instantânea de Tela**: Se o paciente não atender (no-show), o painel do médico deve ser desobstruído imediatamente aos 45s para permitir a próxima chamada.

Precisamos definir o protocolo de comunicação cliente-servidor para entrega desses eventos em tempo real com latência inferior a 100 ms.

---

## 2. Drivers de Decisão

- **Latência de Entrega**: Notificação instantânea ($\le 50\text{ ms}$) para não prejudicar o ring timeout de 45s.
- **Eficiência de Recursos**: Evitar milhares de requisições periódicas de *polling* saturando o FastAPI e o banco.
- **Suporte Multi-Instância**: Capacidade de despachar eventos gerados por workers em segundo plano (ARQ) para clientes conectados em qualquer réplica do backend.

---

## 3. Opções Consideradas

### Opção 1: Short Polling HTTP (Requisições a cada 3 segundos)
O frontend consulta periodicamente um endpoint `/fila/meu-status`.
- *Prós*: Implementação trivial no frontend.
- *Contras*: Atraso médio de 1,5 a 3 segundos para o paciente perceber a chamada do médico (reduzindo a janela de 45s para 42s); sobrecarga maciça de requisições inúteis no servidor em horários de pico.

### Opção 2: Server-Sent Events (SSE)
Canal unidirecional do servidor para o cliente sobre HTTP.
- *Prós*: Simples e compatível com HTTP/2.
- *Contras*: Unidirecional (o paciente não pode responder confirmação de recebimento pelo mesmo canal); problemas de limite de conexões simultâneas em navegadores antigos sob HTTP/1.1; reconexões complexas em redes móveis 4G oscilantes.

### Opção 3: WebSockets Conectados ao Valkey Pub/Sub
Estabelecer conexão persistente WebSocket bidirecional autenticada via JWT. O backend utiliza o **Pub/Sub do Valkey** como *message broker* central de sinalização entre instâncias do FastAPI e os workers do ARQ.
- *Prós*: Bidirecionalidade com latência mínima ($\le 20\text{ ms}$); o paciente recebe a notificação da chamada e envia o *ack* de recebimento pelo mesmo canal; os canais Valkey (`canal:org_{id}:paciente_{id}` e `canal:org_{id}:medico_{id}`) permitem broadcast eficiente entre múltiplos pods/contêineres; baixo overhead de rede em conexões móveis.
- *Contras*: Exige gerenciamento de estado de conexões ativas na memória de cada processo da API.

---

## 4. Decisão

Adotamos a **Opção 3: WebSockets Conectados ao Valkey Pub/Sub**.

### Diretrizes de Execução:
1. **Autenticação no Handshake**: A conexão WebSocket é autenticada através do token JWT fornecido no query parameter de conexão (`/ws/sinalizacao?token=...`).
2. **Canais Segregados por Ator**:
   - `ws:org_{org_id}:paciente_{paciente_id}` (notificações de fila e toque de chamada).
   - `ws:org_{org_id}:profissional_{profissional_id}` (desobstrução de tela e alertas clínicos).
3. **Eventos Chave**:
   - `FILA_POSICAO_ATUALIZADA`: Notifica nova posição e TME estimado.
   - `CHAMADA_RECEBIDA`: Dispara alerta audiovisual do ring timeout de 45s.
   - `NO_SHOW_REGISTRADO`: Libera a tela do médico e encerra a chamada não atendida.
   - `DETERIORACAO_ALERTA`: Sinaliza piora clínica prioritária na tela dos gestores.

---

## 5. Consequências

### Positivas:
- **Experiência em Tempo Real**: Paciente e médico têm percepção instantânea de eventos sem atrasos de polling.
- **Precisão Cirúrgica do SLA**: O paciente começa a ouvir o toque da chamada menos de 50 ms após o médico clicar em "Chamar Próximo".

### Negativas / Riscos Mitigados:
- *Quedas de Conexão em Túneis ou Redes Móveis*: O cliente frontend implementa reconexão automática com *exponential backoff* e sincronização do último estado recebido via REST em caso de reconexão.
