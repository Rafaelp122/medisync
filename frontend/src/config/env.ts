/**
 * Inversão de Controle e Configurações de Ambiente do Frontend (ADR-009 / ADR-011).
 *
 * Centraliza a leitura das variáveis de ambiente Vite (import.meta.env)
 * para governar flags de demonstração, provedores padrão e URLs de API
 * sem espalhar condicionais mágicas ou expor atalhos de teste em produção.
 */

export const env = {
  /** URL base da API REST/WebSocket (padrão: origin ou localhost:5173 via proxy) */
  apiBaseUrl:
    import.meta.env.VITE_API_BASE_URL ||
    (typeof window !== "undefined" && window.location?.origin && window.location.origin !== "null"
      ? window.location.origin
      : "http://localhost:5173"),

  /** Identificador padrão do Tenant (Organização de Saúde) */
  defaultTenantId: import.meta.env.VITE_TENANT_ID || "1",

  /**
   * Habilita recursos facilitadores de demonstração e teste local (ex: preenchimento
   * rápido de credenciais demo de médico e simulador de assinatura ICP-Brasil).
   *
   * Por padrão, é ativo apenas se explicitamente definido como 'true' ou em modo Vite DEV.
   * Em produção (`import.meta.env.PROD`), é estritamente desligado a menos que VITE_ENABLE_DEMO_HELPERS=true.
   */
  isDemoMode:
    import.meta.env.VITE_ENABLE_DEMO_HELPERS !== undefined
      ? import.meta.env.VITE_ENABLE_DEMO_HELPERS === "true"
      : import.meta.env.DEV,

  /** Provedor padrão de PSC para assinatura digital */
  defaultPscProvider:
    import.meta.env.VITE_DEFAULT_PSC_PROVIDER || (import.meta.env.DEV ? "fake" : "birdid"),
};
