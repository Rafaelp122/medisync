/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_TENANT_ID?: string;
  readonly VITE_ENABLE_DEMO_HELPERS?: string;
  readonly VITE_DEFAULT_PSC_PROVIDER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
