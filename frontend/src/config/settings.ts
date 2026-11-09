/**
 * Módulo canônico de configurações, variáveis de ambiente e constantes do frontend MediSync Express.
 * Validação estrita via Zod com imutabilidade profunda em runtime via Object.freeze.
 * Regras: docs/adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md,
 * docs/adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md e docs/reference/environment/variables.md.
 */

import { z } from "zod";

/**
 * Provedores homologados de PSC para assinatura digital ICP-Brasil (ADR-006 / ADR-009).
 */
export const PSC_PROVIDERS = ["birdid", "safeid", "vidaas", "fake"] as const;
export type PscProvider = (typeof PSC_PROVIDERS)[number];

/**
 * Função utilitária de congelamento recursivo em profundidade para garantir imutabilidade estrita (ADR-009).
 */
export function deepFreeze<T>(obj: T): Readonly<T> {
  if (obj === null || typeof obj !== "object") return obj;
  Object.freeze(obj);
  for (const key of Object.keys(obj)) {
    const value = (obj as Record<string, unknown>)[key];
    if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
      deepFreeze(value);
    }
  }
  return obj as Readonly<T>;
}

/**
 * Schema Zod para as variáveis de ambiente da aplicação cliente web.
 */
export const envSchema = z
  .object({
    /** URL base da API REST e WebSockets */
    apiBaseUrl: z.string().default(""),

    /** Identificador padrão do Tenant (Organização de Saúde) */
    defaultTenantId: z.string().min(1, "Tenant ID obrigatório").default("1"),

    /** Flag de habilitação de atalhos e preenchimentos demo */
    isDemoMode: z.boolean().default(false),

    /** Provedor de assinatura ICP-Brasil em nuvem selecionado por padrão */
    defaultPscProvider: z.enum(PSC_PROVIDERS).default("birdid"),

    /** Modo de execução do Vite (development, test, production) */
    mode: z.string().default("development"),

    /** Flag indicativa de ambiente de desenvolvimento local */
    isDev: z.boolean().default(false),

    /** Flag indicativa de ambiente produtivo */
    isProd: z.boolean().default(false),
  })
  .readonly();

export type EnvConfig = z.infer<typeof envSchema>;

/**
 * Schema Zod para constantes clínicas pétreas (RN02, RN06, US-02, US-07, US-08, US-09).
 */
export const clinicalSchema = z
  .object({
    /** Tolerância máxima de toque de chamada até No-Show em segundos (RF-03, RN02) */
    callRingTtlSeconds: z.number().int().positive().default(45),

    /** SLA planejado de TMA de teleconsulta em segundos (RN06, US-09) */
    tmaPlannedSeconds: z.number().int().min(60).default(900),

    /** Tempo de cooldown para reenvio de código OTP em segundos (US-02) */
    otpCooldownSeconds: z.number().int().positive().default(60),

    /** Tempo de expiração padrão de código OTP em segundos (US-02) */
    otpExpirationSeconds: z.number().int().positive().default(300),
  })
  .readonly();

export type ClinicalConfig = z.infer<typeof clinicalSchema>;

/**
 * Schema Zod para parâmetros operacionais de rede e resiliência (ADR-011, US-01, US-07, US-09).
 */
export const networkSchema = z
  .object({
    /** Intervalo de polling da fila virtual em milissegundos (ADR-011) */
    queuePollingIntervalMs: z.number().int().min(1000).default(5000),

    /** Intervalo de telemetria passiva de TMA em milissegundos (US-09) */
    tmaTelemetryIntervalMs: z.number().int().min(1000).default(30000),

    /** Timeout nativo da consulta ao ViaCEP em milissegundos (US-01) */
    viaCepTimeoutMs: z.number().int().positive().default(5000),

    /** Teto máximo de atraso no backoff exponencial de reconexão WebSocket em milissegundos (US-07) */
    wsBackoffMaxDelayMs: z.number().int().positive().default(5000),
  })
  .readonly();

export type NetworkConfig = z.infer<typeof networkSchema>;

/**
 * Schema Zod para chaves canônicas de armazenamento no navegador (LocalStorage / SessionStorage).
 */
export const storageSchema = z
  .object({
    /** Chave da sessão ativa do paciente (LocalStorage) */
    patientSession: z.string().default("medisync_session"),

    /** Chave da sessão corporativa do médico plantonista (LocalStorage) */
    doctorSession: z.string().default("medisync_doctor_session"),

    /** Chave do tenant selecionado no navegador (LocalStorage) */
    tenantId: z.string().default("tenant_id"),

    /** Chave de dispensa do convite de biometria Passkeys (SessionStorage) */
    passkeyDismissed: z.string().default("medisync_passkey_invite_dismissed"),
  })
  .readonly();

export type StorageConfig = z.infer<typeof storageSchema>;

/**
 * Schema Zod para credenciais e valores de demonstração clínica protegidos (US-07, US-09).
 */
export const demoSchema = z
  .object({
    /** E-mail padrão do médico de plantão para preenchimento de teste rápido */
    doctorEmail: z.string().default("eduardo.rocha@medisync.com.br"),

    /** Senha do médico de demonstração clínica */
    doctorPassword: z.string().default("Medisync@2026"),

    /** Token de autorização simulado para PSC em demonstração */
    pscToken: z.string().default("demo-psc-token-123"),
  })
  .readonly();

export type DemoConfig = z.infer<typeof demoSchema>;

/**
 * Schema canônico unificado de configurações do frontend MediSync Express.
 */
export const settingsSchema = z
  .object({
    env: envSchema,
    clinical: clinicalSchema,
    network: networkSchema,
    storage: storageSchema,
    demo: demoSchema,
  })
  .readonly();

export type Settings = z.infer<typeof settingsSchema>;

/**
 * Normaliza e valida um mapa bruto de variáveis de ambiente gerando um objeto Settings imutável.
 * Permite injeção de mapas parciais ou mocks em testes unitários sem poluir o runtime global.
 *
 * @param rawEnv Mapa de variáveis brutas (padrão: import.meta.env)
 * @returns Instância congelada de Settings
 */
export function createSettings(rawEnv: Record<string, unknown> = import.meta.env): Settings {
  const isDev = Boolean(rawEnv.DEV);
  const isProd = Boolean(rawEnv.PROD);
  const mode = typeof rawEnv.MODE === "string" ? rawEnv.MODE : isDev ? "development" : "production";

  // Resolução da URL base da API
  let apiBaseUrl =
    typeof rawEnv.VITE_API_BASE_URL === "string" ? rawEnv.VITE_API_BASE_URL.trim() : "";
  if (
    !apiBaseUrl &&
    typeof window !== "undefined" &&
    window.location?.origin &&
    window.location.origin !== "null"
  ) {
    apiBaseUrl = window.location.origin;
  }

  // Resolução do Tenant ID
  const rawTenantId = typeof rawEnv.VITE_TENANT_ID === "string" ? rawEnv.VITE_TENANT_ID.trim() : "";
  const defaultTenantId = rawTenantId || "1";

  // Resolução da flag isDemoMode
  let isDemoMode: boolean;
  if (rawEnv.VITE_ENABLE_DEMO_HELPERS !== undefined && rawEnv.VITE_ENABLE_DEMO_HELPERS !== "") {
    isDemoMode =
      rawEnv.VITE_ENABLE_DEMO_HELPERS === "true" || rawEnv.VITE_ENABLE_DEMO_HELPERS === true;
  } else {
    isDemoMode = isDev;
  }
  // Salvaguarda fail-fast: em produção, desativa atalhos demo a menos que explicitamente true
  if (isProd && rawEnv.VITE_ENABLE_DEMO_HELPERS !== "true") {
    isDemoMode = false;
  }

  // Resolução do provedor PSC
  let rawPsc =
    typeof rawEnv.VITE_DEFAULT_PSC_PROVIDER === "string"
      ? rawEnv.VITE_DEFAULT_PSC_PROVIDER.trim()
      : "";
  if (!rawPsc) {
    rawPsc = isDev ? "fake" : "birdid";
  }

  const parsed = settingsSchema.parse({
    env: {
      apiBaseUrl,
      defaultTenantId,
      isDemoMode,
      defaultPscProvider: rawPsc,
      mode,
      isDev,
      isProd,
    },
    clinical: {},
    network: {},
    storage: {},
    demo: {},
  });

  return deepFreeze(parsed);
}

/**
 * Instância única canônica de configurações do frontend MediSync Express.
 * Centraliza variáveis de ambiente, parâmetros de rede e constantes clínicas pétreas.
 * Regras: docs/adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md,
 * docs/adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md e docs/reference/environment/variables.md.
 */
export const settings: Settings = createSettings(import.meta.env);
