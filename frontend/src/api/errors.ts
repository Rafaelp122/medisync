export interface InvalidParam {
  name: string;
  reason: string;
}

export interface ProblemDetails {
  type?: string;
  title?: string;
  status: number;
  detail: string;
  instance?: string;
  code?: string;
  request_id?: string;
  invalid_params?: ReadonlyArray<InvalidParam>;
  [key: string]: unknown;
}

export class ProblemDetailsError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.detail || problem.title || `HTTP error ${problem.status}`);
    this.name = "ProblemDetailsError";
    this.status = problem.status;
    this.problem = problem;
  }

  get detail(): string {
    return this.problem.detail;
  }

  get code(): string | undefined {
    return typeof this.problem.code === "string" ? this.problem.code : undefined;
  }

  get requestId(): string | undefined {
    return typeof this.problem.request_id === "string" ? this.problem.request_id : undefined;
  }

  get invalidParams(): ReadonlyArray<InvalidParam> | undefined {
    return Array.isArray(this.problem.invalid_params) ? this.problem.invalid_params : undefined;
  }
}

export function isProblemDetailsError(error: unknown): error is ProblemDetailsError {
  return error instanceof ProblemDetailsError;
}

function isNetworkFailureMessage(message: string): boolean {
  return (
    message.includes("Failed to fetch") ||
    message.includes("NetworkError") ||
    message.includes("Load failed")
  );
}

function getErrorName(error: unknown): string | undefined {
  if (typeof error === "object" && error !== null && "name" in error) {
    const name = (error as { name?: unknown }).name;
    return typeof name === "string" ? name : undefined;
  }
  return undefined;
}

function getErrorMessage(error: unknown): string | undefined {
  if (typeof error === "object" && error !== null && "message" in error) {
    const msg = (error as { message?: unknown }).message;
    return typeof msg === "string" ? msg : undefined;
  }
  return undefined;
}

export function toProblemDetailsError(error: unknown, statusFallback = 500): ProblemDetailsError {
  if (error instanceof ProblemDetailsError) {
    return error;
  }
  const errorName = getErrorName(error);
  const errorMessage = getErrorMessage(error);

  if (errorName === "TimeoutError") {
    return new ProblemDetailsError({
      status: 504,
      title: "Tempo de resposta esgotado",
      detail: errorMessage || "Tempo limite da requisição esgotado.",
      code: "TIMEOUT",
    });
  }
  if (errorName === "AbortError") {
    return new ProblemDetailsError({
      status: 408,
      title: "Requisição cancelada",
      detail: errorMessage || "A requisição foi cancelada antes de ser concluída.",
      code: "ABORTED",
    });
  }

  if (error instanceof Error) {
    const obj = error as unknown as Record<string, unknown>;
    if (typeof obj.status !== "number" && typeof obj.detail !== "string") {
      const detail = error.message || "Erro de comunicação com o servidor";
      return new ProblemDetailsError({
        status: statusFallback,
        detail,
        ...(isNetworkFailureMessage(detail) ? { code: "NETWORK_ERROR" } : {}),
      });
    }
  }
  if (typeof error === "object" && error !== null) {
    const obj = error as Record<string, unknown>;
    const status = typeof obj.status === "number" ? obj.status : statusFallback;
    const detail =
      typeof obj.detail === "string"
        ? obj.detail
        : typeof obj.title === "string"
          ? obj.title
          : "Erro inesperado na requisição";
    return new ProblemDetailsError({
      ...obj,
      status,
      detail,
    });
  }
  return new ProblemDetailsError({
    status: statusFallback,
    detail: typeof error === "string" ? error : "Erro de comunicação com o servidor",
  });
}

export function extractProblemDetail(
  error: unknown,
  fallback = "Ocorreu um erro inesperado",
): string {
  if (!error) return fallback;
  if (isProblemDetailsError(error)) {
    return error.problem.detail || error.problem.title || error.message || fallback;
  }
  if (typeof error === "object" && error !== null) {
    const err = error as Record<string, unknown>;
    if (typeof err.detail === "string") return err.detail;
    if (typeof err.title === "string") return err.title;
    if (typeof err.message === "string") return err.message;
    if (err.problem && typeof err.problem === "object") {
      const prob = err.problem as Record<string, unknown>;
      if (typeof prob.detail === "string") return prob.detail;
    }
  }
  if (typeof error === "string") return error;
  return fallback;
}

export function extractProblemStatus(error: unknown, fallback = 500): number {
  if (!error) return fallback;
  if (isProblemDetailsError(error)) return error.status;
  if (typeof error === "object" && error !== null) {
    const err = error as Record<string, unknown>;
    if (typeof err.status === "number") return err.status;
  }
  return fallback;
}

export interface HumanizedError {
  title: string;
  detail: string;
  retryable: boolean;
}

/**
 * Traduz erros técnicos (RFC 7807, Network, Timeout, 403, 429, 5xx) em mensagens
 * acolhedoras e acionáveis em português para a interface.
 */
export function getHumanizedErrorMessage(
  error: unknown,
  fallback = "Ocorreu um erro inesperado ao processar sua solicitação.",
): HumanizedError {
  const status = extractProblemStatus(error);
  const rawDetail = extractProblemDetail(error, fallback);
  let code: string | undefined;

  if (isProblemDetailsError(error)) {
    code = error.code;
  } else if (typeof error === "object" && error !== null) {
    const err = error as Record<string, unknown>;
    code =
      (err.code as string | undefined) ||
      (err.problem && typeof err.problem === "object"
        ? ((err.problem as Record<string, unknown>).code as string | undefined)
        : undefined);
  }

  // Falha de Conexão ou Rede
  if (isNetworkFailureMessage(rawDetail) || code === "NETWORK_ERROR") {
    return {
      title: "Falha de conexão com a internet",
      detail:
        "Não foi possível conectar aos servidores do MediSync. Verifique sua conexão e tente novamente.",
      retryable: true,
    };
  }

  // Timeout / Tempo esgotado (504, TIMEOUT)
  if (status === 504 || code === "TIMEOUT" || rawDetail.toLowerCase().includes("timeout")) {
    return {
      title: "Tempo de resposta esgotado",
      detail:
        "O servidor demorou mais do que o esperado para responder. Por favor, tente novamente.",
      retryable: true,
    };
  }

  // Permissão negada (403 Forbidden)
  if (status === 403 || code === "FORBIDDEN") {
    return {
      title: "Acesso não autorizado",
      detail:
        rawDetail && rawDetail !== fallback && rawDetail !== "Forbidden"
          ? rawDetail
          : "Seu perfil não possui permissão para executar esta operação.",
      retryable: false,
    };
  }

  // Limite de taxa excedido (429 Too Many Requests)
  if (status === 429 || code === "RATE_LIMIT_EXCEEDED" || code === "TOO_MANY_REQUESTS") {
    return {
      title: "Muitas tentativas em sequência",
      detail:
        rawDetail && rawDetail !== fallback && rawDetail !== "Too Many Requests"
          ? rawDetail
          : "Muitas requisições em sequência. Aguarde alguns instantes antes de tentar novamente.",
      retryable: true,
    };
  }

  // Indisponibilidade momentânea de gateway/upstream (502, 503)
  if (status === 502 || status === 503) {
    return {
      title: "Serviço temporariamente indisponível",
      detail:
        "O serviço está passando por uma breve instabilidade de comunicação. Por favor, tente novamente em instantes.",
      retryable: true,
    };
  }

  // Erros internos de Servidor (500+) ou código INTERNAL_SERVER_ERROR
  if (
    status >= 500 ||
    code === "INTERNAL_SERVER_ERROR" ||
    rawDetail.toLowerCase().includes("internal server error")
  ) {
    return {
      title: "Instabilidade temporária no servidor",
      detail:
        "Tivemos uma oscilação temporária ao comunicar com nossos servidores. Por favor, tente novamente em alguns instantes — seus dados continuam preenchidos.",
      retryable: true,
    };
  }

  // Erros de Validação ou Regras de Domínio Clínicas (400, 409, 422)
  return {
    title: "Atenção aos dados informados",
    detail: rawDetail,
    retryable: false,
  };
}
