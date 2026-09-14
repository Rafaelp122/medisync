# [ADR-008] Assinatura Digital ICP-Brasil em Nuvem via PSCs e Porta Desacoplada

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (PREM-02, RF-07, RNF-06, RNF-09) |

---

## 1. Contexto e Declaração do Problema

Receitas médicas, atestados e solicitações de exames emitidos em ambiente de telemedicina no Brasil possuem validade jurídica condicionada ao uso de certificados digitais válidos na Infraestrutura de Chaves Públicas Brasileira (ICP-Brasil), conforme exigido pela Portaria GM/MS nº 467/2020 e Resolução CFM nº 2.314/2022.

Historicamente, certificados médicos eram emitidos em mídias físicas (Smartcards ou Tokens USB do tipo A3), o que cria barreiras severas em aplicações web modernas (necessidade de extensões proprietárias de navegador, drivers incompatíveis com Linux/macOS e impossibilidade de emissão via dispositivos móveis).

Precisamos definir um padrão de emissão e assinatura digital que seja seguro, moderno, multiplataforma e 100% desacoplado de fornecedores proprietários específicos (RNF-09).

---

## 2. Drivers de Decisão

- **Conformidade Legal**: Assinatura digital válida perante o validador oficial de documentos digitais do Instituto Nacional de Tecnologia da Informação (ITI).
- **Usabilidade Médica**: Permitir que o médico assine documentos no navegador sem exigir a instalação de drivers locais ou plugins Java/C++.
- **Neutralidade de Fornecedor (*Vendor Lock-in Free*)**: Suportar múltiplos Provedores de Serviço de Confiança (PSCs homologados pelo ITI, tais como BirdID, SAFE-ID, Vidaas, Serasa).
- **Resiliência de Interface**: Falhas transitórias ou lentidão no provedor de assinatura não podem travar a tela médica.

---

## 3. Opções Consideradas

### Opção 1: Suporte a Tokens Físicos USB/Smartcard no Navegador
Exigir que o médico conecte um token USB em seu computador e instalar uma aplicação local nativa (WebSocket local) para assinar o PDF.
- *Prós*: Muitos médicos já possuem o token físico tradicional.
- *Contras*: Suporte técnico insustentável (falhas de driver, bloqueios por antivírus, incompatibilidade com SOs modernos); impossível de operar em tablets ou smartphones; quebra a premissa de pronto-atendimento ágil.

### Opção 2: Integração Proprietária com um Único Provedor Comercial
Fechar o código do backend acoplado a uma API específica de um único fornecedor (ex.: apenas BirdID).
- *Prós*: Rápido de prototipar.
- *Contras*: Viola o princípio open source do projeto e cria dependência comercial; se uma prefeitura possuir contrato corporativo com outro PSC (ex.: Vidaas), o software torna-se inútil.

### Opção 3: Porta Abstrata (`ICPBrasilSignerPort`) com Assinatura em Nuvem via OAuth2
Definir uma interface abstrata em Python puro (`typing.Protocol`) e utilizar o padrão PAdES através da biblioteca `PyHanko` em conjunto com a API REST/OAuth2 do PSC contratado pela instituição.
- *Prós*: Usabilidade total no navegador (o médico autoriza no app do celular via push OTP); 100% desacoplado; troca de provedor por simples injeção de dependência no FastAPI; retry assíncrono via worker do ARQ em caso de lentidão do PSC.
- *Contras*: Exige que o médico possua certificado A3 em nuvem ativo.

---

## 4. Decisão

Adotamos a **Opção 3: Porta Abstrata (`ICPBrasilSignerPort`) com Assinatura em Nuvem via OAuth2**.

### Diretrizes de Execução:
1. **Contrato de Porta no Domínio**:
   ```python
   class ICPBrasilSignerPort(Protocol):
       async def assinar_pades(
           self, pdf_bytes: bytes, credenciais_psc: dict[str, str]
       ) -> bytes:
           ...
   ```
2. **Geração de PDF/A com ReportLab**: O backend gera o PDF em formato arquivístico com QR Code apontando para o verificador oficial.
3. **Assinatura PAdES com PyHanko**: O adaptador invoca o endpoint de assinatura do PSC e aplica a assinatura com carimbo do tempo.
4. **Retry Desacoplado**: Se o PSC demorar mais de 10 segundos, o atendimento é concluído clinicamente e a finalização da assinatura é despachada para o worker ARQ em segundo plano.

---

## 5. Consequências

### Positivas:
- **Zero Instalação Local**: O médico precisa apenas do navegador moderno para atender e prescrever.
- **Portabilidade Institucional**: Prefeituras e clínicas podem configurar seu próprio provedor de PSC via variáveis de ambiente.

### Negativas / Riscos Mitigados:
- *Dependência de API Externa*: Mitigada pelo desacoplamento da porta e pelo mecanismo de retry com notificação posterior do envio da receita ao paciente.
