# [ADR-007] Desacoplamento do Servidor de Mídia WebRTC via LiveKit SFU

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (PREM-01, RF-07, RN06, RNF-04, RNF-09) |

---

## 1. Contexto e Declaração do Problema

A teleconsulta médica no MediSync Express requer transmissão bidirecional de áudio e vídeo em tempo real sob canais criptografados (SRTP), com latência de transporte estritamente inferior a 150 ms (RNF-04).

Além disso, a Resolução CFM nº 2.314/2022 e a invariante RN06 determinam que a chamada médica não pode ser encerrada automaticamente por tempo decorrido, dependendo exclusivamente da soberania do médico ao finalizar formalmente o atendimento no prontuário.

Precisamos definir a arquitetura de roteamento de mídia sem sobrecarregar o backend em Python.

---

## 2. Drivers de Decisão

- **Latência de Transporte**: $\le 150\text{ ms}$ em condições de rede 4G/5G/Banda Larga (RNF-04).
- **Desacoplamento Arquitetural**: O backend Python não deve manipular pacotes de mídia RTP/SRTP (RNF-09).
- **Escalabilidade e Eficiência**: Roteamento de vídeo escrito em linguagem de alta performance para concorrência de rede (Go/Rust/C++).
- **Licenciamento Permissivo**: Software open source compatível com os princípios do projeto.

---

## 3. Opções Consideradas

### Opção 1: WebRTC Ponto a Ponto (P2P Mesh)
Conexão direta entre o navegador do médico e o do paciente via STUN/TURN, sem servidor intermediário de mídia.
- *Prós*: Sem custo de servidor de mídia adicional.
- *Contras*: Exige upload dobrado caso múltiplos participantes entrem (ex.: médico assistente ou acompanhante legal); instável em redes móveis com NAT simétrico; impossibilita telemetria avançada de rede e gravação segura auditável quando exigida.

### Opção 2: Servidor de Mídia Embutido em Python (`aiortc`)
Terminar o WebRTC diretamente no processo FastAPI usando a biblioteca Python `aiortc`.
- *Prós*: Tudo em um único ecossistema de linguagem.
- *Contras*: O Python não foi desenhado para processamento intensivo de streams de mídia em tempo real; a decodificação e repasse de pacotes VP8/H.264 saturariam a CPU e o loop do `asyncio`, congelando as APIs REST do sistema.

### Opção 3: Servidor SFU Desacoplado via LiveKit
Utilizar o **LiveKit SFU** (Selective Forwarding Unit), um servidor open source em Go de ultra-alta performance.
- *Prós*: Latência ultrabaixa (< 100 ms); suporte nativo a simulcast (adaptação automática para redes 3G/4G precárias); o backend MediSync atua **apenas como autoridade de autorização**, emitindo tokens JWT assinados com permissões de sala; a sala só é encerrada quando o backend recebe a conclusão do prontuário médico e invoca `delete_room` via API REST.
- *Contras*: Adiciona um binário/contêiner ao deploy geral.

---

## 4. Decisão

Adotamos a **Opção 3: Servidor SFU Desacoplado via LiveKit**.

### Diretrizes de Execução:
1. **Isolamento Total de Tráfego**: Fluxos de mídia trafegam exclusivamente entre os navegadores e a porta UDP do LiveKit.
2. **Tokens Segregados por Tenant**: O backend emite tokens LiveKit com a claim `room = f"org_{org_id}_atendimento_{atendimento_id}"`.
3. **Respeito ao Ato Médico (RN06)**: O token de sala não possui TTL rígido de expiração de sessão; a sala só é fechada via chamada explícita `livekit_client.room_service.delete_room()` disparada pela finalização do PEP pelo médico.
4. **Topologia de Produção e Transposição de NAT/Firewall**:
   - Em produção, abrir faixa de portas UDP `50000-60000` (mídia WebRTC ICE), porta `7880 TCP` (sinalização) e porta `7881 TCP` (fallback).
   - Para furar NAT simétrico agressivo em redes celulares 3G/4G brasileiras e firewalls hospitalares que bloqueiam UDP, ativar o servidor TURN embutido do LiveKit com suporte a **TURNS sobre TLS na porta 443 TCP ou 5349 TCP**, garantindo que a chamada médica nunca falhe por restrição de rede.

---

## 5. Consequências

### Positivas:
- **Estabilidade do Backend**: O FastAPI e o Valkey dedicam 100% de seus recursos a regras de negócio e concorrência de fila.
- **Qualidade de Áudio e Vídeo**: O LiveKit gerencia oscilações de rede sem travamentos, aplicando degradação graciosa para voz quando a largura de banda cai.

### Negativas / Riscos Mitigados:
- *Complexidade de Rede em Produção (Firewall / NAT Simétrico)*: Mitigada pela configuração de STUN público e servidor TURN com fallback TCP/TLS na porta 443, detalhado no guia de infraestrutura da [RFC-006](../rfcs/RFC-006-Teleconsulta-WebRTC-e-Assinatura-ICP.md).
