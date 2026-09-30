# [ADR-005] Desacoplamento do Servidor de Mídia WebRTC via LiveKit SFU

| Metadado | Detalhamento |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview](../03-architecture/overview.md), [Telemedicina](../03-architecture/compliance-and-telemedicine.md) (RNF-04, PREM-01) |

---

## 1. Contexto e Declaração do Problema

A teleconsulta exige comunicação bidirecional de áudio e vídeo com latência de transporte $\le 150\text{ ms}$ sob criptografia SRTP (RNF-04). A arquitetura precisa:
1. Impedir que o processamento pesado de pacotes de mídia degrade a CPU do backend Python.
2. Garantir conexão estável mesmo em redes celulares (4G/3G) e firewalls hospitalares restritivos.
3. Permitir a entrada de terceiros (responsável familiar ou especialista regulador) sem perda de qualidade.

---

## 2. Drivers de Decisão

* **Isolamento de Carga de Mídia**: O runtime Python deve cuidar exclusivamente da lógica clínica, do prontuário e das transições de fila.
* **Topologia SFU (Selective Forwarding Unit)**: Roteamento inteligente de fluxos de vídeo sem recodificação pesada.
* **Travessia de NAT e Firewalls**: Suporte obrigatório a STUN/TURN e TURNS (porta 443/TCP) para transpor bloqueios corporativos.

---

## 3. Opções Consideradas

### Opção 1: WebRTC Puro Peer-to-Peer (P2P)
* *Prós*: Sem necessidade de servidor de mídia intermediário.
* *Contras*: Falhas frequentes de conexão entre redes móveis e hospitais; banda de upload sobrecarregada ao incluir familiares; impossibilidade de supervisão técnica.

### Opção 2: Roteamento de Mídia em Python (`aiortc`)
* *Prós*: Mantém todo o ecossistema dentro do Python.
* *Contras*: O Global Interpreter Lock (GIL) e a sobrecarga de manipulação de pacotes RTP em Python saturam a CPU, colapsando a API de atendimento.

### Opção 3: Servidor Especializado LiveKit SFU em Go (Adotada)
* *Prós*: Escrito em Go com desempenho ultra-otimizado; latência sub-100ms; protocolo moderno baseado em WebRTC; suporte embutido a TURNS; o backend FastAPI apenas gera tokens JWT efêmeros assinados; SDKs web/mobile maduros.
* *Contras*: Exige a execução de um contêiner separado na orquestração Docker Compose.

---

## 4. Decisão

Adotamos a **Opção 3: Desacoplamento de Mídia via LiveKit SFU Server**.

### Diretrizes de Execução:
1. O backend emite tokens JWT com *Video Grants* específicos por atendimento (`org_{id}_atend_{id}`).
2. O tráfego de mídia corre exclusivamente entre o navegador do paciente/médico e o LiveKit SFU.
3. Respeito irrestrito ao ato médico: o servidor de mídia nunca interrompe uma consulta por tempo.

---

## 5. Consequências

### Positivas:
* **Desempenho Impecável**: CPU do backend Python preservada a 100% para regras de negócio.
* **Resiliência em Redes Restritivas**: Conexão mantida via TURNS (porta 443) quando UDP for bloqueado.
