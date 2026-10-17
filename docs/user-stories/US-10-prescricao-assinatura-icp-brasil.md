# US-10 — Prescrição Médica, Salvaguardas Farmacêuticas e Assinatura ICP-Brasil

> **Requisito Base:** RF-07  
> **Invariantes Relacionadas:** Portaria SVS/MS 344/98, RDC ANVISA 20/2011, Resolução CFM 2.314/2022  
> **Personas:** Dr. Eduardo Rocha (Médico) e Juliana Silva (Paciente)  
> **Módulos:** `consultation`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** médico prescrevendo medicamentos em ambiente digital (Dr. Eduardo Rocha),  
**Quero** que a plataforma valide salvaguardas farmacêuticas legais, gere um documento PDF/A-1b inviolável e o assine com certificado digital ICP-Brasil PAdES contendo QR Code do ITI,  
**Para que** a paciente (Juliana) consiga dispensar a receita em qualquer farmácia do Brasil e o ato médico esteja plenamente blindado contra falsificações.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Prescrição de Antimicrobianos em 2 vias com validação pública (Fatia Farmacêutica)
- **Dado que** prescrevo um antibiótico sujeito a controle sanitário (ex: Amoxicilina - RDC ANVISA 20/2011),
- **Quando** solicito a emissão e assinatura do documento clínico,
- **Então** o sistema gera automaticamente o documento em formato de preservação digital PDF/A contendo a 1ª via (Farmácia) e a 2ª via (Paciente),
- **E** inclui o código QR Code apontando para o canal oficial de validação pública da assinatura digital,
- **E** aplica a assinatura digital ICP-Brasil com carimbo de tempo oficial,
- **E** disponibiliza o token seguro de validação pública e download (HTTP 200 OK).

### Cenário 2: Bloqueio estrito de substâncias proibidas em telemedicina (Fatia de Salvaguarda)
- **Dado que** o médico tenta prescrever substância sujeita a Notificação de Receita A ou B (ex: Morfina, Clonazepam, Zolpidem),
- **Quando** o sistema realiza a validação farmacêutica preliminar do documento,
- **Então** a emissão é imediatamente bloqueada com erro de validação (HTTP 422 Unprocessable Entity),
- **E** apresenta alerta legal informando que tais substâncias exigem talonário físico específico e não podem ser emitidas por teleconsulta (Portaria SVS/MS 344/98).

### Cenário 3: Validação pública de autenticidade por farmácias e pacientes (Fatia de Verificação)
- **Dado que** um farmacêutico ou paciente faz a leitura do QR Code presente no receituário emitido,
- **Quando** consulta a URL de validação em `GET /api/v1/documents/validate/{token_validacao}`,
- **Então** o sistema confirma a validade e integridade criptográfica da assinatura ICP-Brasil,
- **E** exibe o nome completo do médico emissor, CRM, UF e data/hora oficial UTC da emissão,
- **E** autoriza a visualização e download seguro do PDF original assinado.

---

## 3. Contrato de API

* **Finalização de Documento e Assinatura:** `POST /api/v1/consultations/{atendimento_id}/documents/{documento_id}/sign`
* **Download Público de Documento:** `GET /api/v1/documents/download/{token_validacao}`
* **Validação Pública de Autenticidade:** `GET /api/v1/documents/validate/{token_validacao}`
  *Resposta (`200 OK`):*
  ```json
  {
    "documento_valido": true,
    "medico_emissor": "Dr. Eduardo Rocha",
    "crm_uf": "123456/SP",
    "assinado_em": "2026-10-17T09:40:00Z",
    "tipo_documento": "RECEITA_SIMPLES",
    "certificado_emissor": "ICP-Brasil / PSC Nuvem"
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Salvaguardas Farmacêuticas:** Blacklist de Notificação A/B e 2 vias para antimicrobianos (`src/modules/consultation/domain/models/documento_clinico.py`).
- [x] **Compilador PDF/A:** ReportLab gerando PDF/A-1b com QR Code do ITI (`src/modules/consultation/infrastructure/pdf_generator.py`).
- [x] **Assinador ICP-Brasil:** Adaptador PyHanko aplicando assinatura digital padrão ICP-Brasil PAdES (`src/modules/consultation/infrastructure/pyhanko_signer.py`).
- [x] **Armazenamento em Nuvem:** Adaptador MinIO/S3 com chaves canônicas e portal de validação público (`src/modules/consultation/infrastructure/s3_storage.py`).
- [x] **Testes Automatizados:**
  - `tests/unit/test_pyhanko_signer.py`
  - `tests/unit/test_pdf_generator.py`
  - `tests/integration/test_document_signing_endpoint.py`
  - `tests/integration/test_storage_and_validation_portal.py`
