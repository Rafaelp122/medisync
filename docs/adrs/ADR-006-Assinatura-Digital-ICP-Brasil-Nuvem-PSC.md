# [ADR-006] Assinatura Digital ICP-Brasil em Nuvem via PSCs e PAdES

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview](../03-architecture/overview.md), [Telemedicina](../03-architecture/compliance-and-telemedicine.md) (RNF-06, PREM-02) |

---

## 1. Contexto e Declaração do Problema

Receitas médicas, atestados e pedidos de exames emitidos em telemedicina no Brasil exigem conformidade com a MP nº 2.200-2/2001 e Resolução CFM nº 2.314/2022:
1. **Validade Farmacêutica Mandatória**: Para medicamentos antimicrobianos (RDC 20/2011) e controle especial (Portaria 344/98 Lista C1), farmácias exigem assinatura qualificada no padrão da Infraestrutura de Chaves Públicas Brasileira (ICP-Brasil).
2. **Inviabilidade de Tokens Físicos**: Em um pronto-atendimento virtual 24/7, os médicos operam remotamente. Exigir tokens USB ou leitores de cartão smartcard cria barreiras de instalação de drivers e incompatibilidade com navegadores web modernos.

---

## 2. Drivers de Decisão

* **Validade Jurídica e Sanitária**: Aceitação garantida em qualquer farmácia do território nacional e aprovação no validador oficial do Instituto Nacional de Tecnologia da Informação (ITI).
* **Experiência do Usuário Médico**: Assinatura rápida sem necessidade de instalação de plugins desktop ou extensões proprietárias de navegador.
* **Desacoplamento de Provedor**: Capacidade de operar com múltiplos provedores de certificados em nuvem (BirdID, SafeID, Vidaas).

---

## 3. Opções Consideradas

### Opção 1: Assinatura Eletrônica Simples (Gov.br / Hash)
* *Prós*: Gratuita e fácil de implementar.
* *Contras*: Não atende à legislação sanitária para medicamentos controlados e antimicrobianos, gerando recusa farmacêutica imediata para os pacientes.

### Opção 2: Certificado Digital A3 em Token Físico USB
* *Prós*: Já possuído por alguns médicos tradicionais.
* *Contras*: Navegadores modernos não acessam portas USB diretamente sem extensões locais frágeis (*PKCS#11*); incompatível com tablets e notebooks corporativos restritivos.

### Opção 3: Assinatura PAdES em Nuvem via Provedores PSC (OAuth2) e PyHanko (Adotada)
* *Prós*: Totalmente integrada via APIs REST e fluxo padrão OAuth2; os médicos autorizam a assinatura diretamente pelo celular via push/OTP; geração de arquivos PDF/A assinados com padrão PAdES-LTV (com carimbo do tempo) utilizando a biblioteca `PyHanko`.
* *Contras*: Exige credenciamento ou conta ativa do médico junto a um PSC homologado pelo ITI.

---

## 4. Decisão

Adotamos a **Opção 3: Assinatura ICP-Brasil em Nuvem via PSCs e biblioteca PyHanko**.

### Diretrizes de Execução:
1. Interface do médico integrada ao PSC via porta desacoplada `ICPBrasilSignerPort`.
2. Emissão do documento em formato PDF/A via `ReportLab` contendo declaração legal e QR Code de autenticação.
3. Aplicação do carimbo criptográfico PAdES pelo `PyHanko` e armazenamento no bucket S3/MinIO.

---

## 5. Consequências

### Positivas:
* **Conformidade Legal 100% Blindada**: Documentos validados com sucesso no portal do ITI (`validador.iti.gov.br`).
* **Mobilidade Total**: Plantonistas assinam de qualquer lugar sem hardware adicional.
