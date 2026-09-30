# Architecture Decision Records (ADRs)

Este diretório é reservado para o registro formal de **Decisões de Arquitetura (ADRs)** do MediSync Express.

## Diretrizes de Governança Ágil (Anti-BDUF)

1. **Decisões Sob Demanda**: Nenhuma ADR é escrita a priori com base em previsões teóricas. As ADRs nascem ao longo do desenvolvimento quando a equipe de engenharia se depara com encruzilhadas técnicas reais e não-triviais.
2. **Critérios de Relevância**: Uma ADR deve ser escrita apenas quando a decisão:
   - Impactar estruturalmente múltiplos módulos;
   - Envolver trade-offs significativos de desempenho, segurança ou manutenibilidade;
   - For de difícil reversão após implementada em código.
3. **Padrão Adotado**: Sugere-se o formato clássico de Michael Nygard:
   - **Título**: `ADR-XXX-descricao-curta.md`
   - **Status**: Proposto, Aceito, Obsoleto ou Substituído
   - **Contexto**: A tensão técnica ou problema real enfrentado
   - **Decisão**: A solução adotada e sua justificação técnica
   - **Consequências**: Os impactos positivos e negativos comprovados
