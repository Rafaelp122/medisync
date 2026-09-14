# [ADR-011] Armazenamento de Documentos Clínicos via Object Storage (S3 / MinIO) e Presigned URLs

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RF-07, RNF-05, RNF-06, RNF-08) |

---

## 1. Contexto e Declaração do Problema

Durante as teleconsultas no MediSync Express, o sistema gera e assina digitalmente documentos em formato PDF/A (receituários simples, antimicrobianos, atestados médicos, pedidos de exames e sumários de prontuário). 

Pela Resolução CFM nº 1.821/2007, prontuários e documentos clínicos devem ser guardados por no mínimo 20 anos. Precisamos de uma solução de armazenamento de arquivos binários que:
1. Escale para milhões de documentos sem inchar o banco de dados relacional.
2. Permita implantações com contêineres replicados horizontalmente sem depender de discos locais compartilhados (NFS).
3. Seja portável para provedores de nuvem pública (AWS S3, Google Cloud Storage) e para infraestruturas locais de municípios pequenos (usando MinIO on-premise).
4. Entregue os arquivos de forma segura e temporária para pacientes e farmácias sem expor o bucket publicamente.

---

## 2. Drivers de Decisão

- **Segurança e Privacidade (LGPD Art. 11)**: Os arquivos não podem ser públicos na internet; o acesso deve ser individualizado e expirar em minutos.
- **Portabilidade Open Source**: Suportar o padrão industrial S3 API tanto em nuvem gerenciada quanto em contêiner local open source.
- **Eficiência de Banco de Dados**: Manter o PostgreSQL dedicado estritamente a dados estruturados e transacionais.

---

## 3. Opções Consideradas

### Opção 1: Armazenamento em Banco Relacional (`BYTEA` / BLOB no PostgreSQL)
Salvar os bytes dos arquivos PDF diretamente em colunas da tabela de documentos.
- *Prós*: Transacionalidade atômica com os registros de prontuário; backup único.
- *Contras*: Inchaço descontrolado do banco (tamanho dos backups de gigabytes para terabytes); lentidão em consultas; saturação de memória do pool de conexões do `asyncpg`.

### Opção 2: Sistema de Arquivos Local do Servidor (`/var/data/medisync`)
Salvar os PDFs no disco do host e expor via endpoint HTTP do FastAPI.
- *Prós*: Simples de implementar no ambiente de desenvolvimento.
- *Contras*: Quebra a portabilidade de múltiplos contêineres Uvicorn/Docker (um contêiner não enxerga o arquivo do outro sem NFS/Ceph complexo); viola o princípio de contêineres descartáveis (*stateless*).

### Opção 3: Object Storage Compatível com API S3 + Presigned URLs
Adotar a API padrão S3, utilizando **MinIO** para desenvolvimento e implantações locais/municipais, e buckets de nuvem (AWS S3 ou Google Cloud Storage) em deploys gerenciados. O download pelo paciente é realizado via **URLs Pré-Assinadas (*Presigned URLs*)** geradas sob demanda com tempo de expiração curto (ex.: 15 minutos).
- *Prós*: Padrão da indústria; desacoplamento total; zero impacto no banco relacional (que guarda apenas o `s3_key` e o hash SHA-256); segurança máxima (o bucket é estritamente privado, sem acesso público direto); compatível com a biblioteca padrão assíncrona `aioboto3`.
- *Contras*: Adiciona o MinIO como serviço opcional no `docker-compose.yml` para ambientes de desenvolvimento ou on-premise.

---

## 4. Decisão

Adotamos a **Opção 3: Object Storage Compatível com API S3 + Presigned URLs**.

### Diretrizes de Execução:
1. **Padrão de Chaves no Bucket**: Organizado logicamente por tenant e atendimento:
   `s3://medisync-docs/{organizacao_id}/atendimentos/{atendimento_id}/{documento_uuid}.pdf`
2. **URLs Pré-Assinadas**: O paciente recebe um link de download com validade máxima de 15 minutos (`expires_in=900`).
3. **Ambiente Local**: O `docker-compose.yml` inclui o serviço MinIO (`minio/minio:latest`) pré-configurado para desenvolvimento e pequenas instalações.

---

## 5. Consequências

### Positivas:
- **Alta Escalabilidade**: Armazenamento praticamente ilimitado com custo por gigabyte ordens de magnitude menor que armazenamento SSD de banco relacional.
- **Privacidade Assegurada**: Links expirados impedem o vazamento de documentos caso URLs sejam compartilhadas acidentalmente.

### Negativas / Riscos Mitigados:
- *Dependência de S3 Client*: Utiliza-se `aioboto3` encapsulado em uma porta (`StoragePort`), permitindo mocks triviais em testes unitários.
