export interface ProblemDetails {
  type?: string;
  title?: string;
  status: number;
  detail: string;
  instance?: string;
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
    return this.problem.code as string | undefined;
  }
}

export function isProblemDetailsError(error: unknown): error is ProblemDetailsError {
  return error instanceof ProblemDetailsError;
}

export function toProblemDetailsError(error: unknown, statusFallback = 500): ProblemDetailsError {
  if (error instanceof ProblemDetailsError) {
    return error;
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
      status,
      detail,
      ...obj,
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
 * Traduz erros técnicos (RFC 7807, Network, 500) em mensagens acolhedoras
 * e acionáveis em português para a interface do paciente.
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
  if (
    rawDetail.includes("Failed to fetch") ||
    rawDetail.includes("NetworkError") ||
    rawDetail.includes("Load failed") ||
    code === "NETWORK_ERROR"
  ) {
    return {
      title: "Falha de conexão com a internet",
      detail:
        "Não foi possível conectar aos servidores do MediSync. Verifique sua conexão e tente novamente.",
      retryable: true,
    };
  }

  // Organização inválida ou cabeçalho de tenant ausente (400, TENANT_INVALIDO)
  if (code === "TENANT_INVALIDO") {
    return {
      title: "Identificação da unidade de saúde",
      detail:
        "Identificador da unidade de saúde inválido ou não informado. Por favor, recarregue a página.",
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

  // Erros de Servidor (500, 502, 503) ou código INTERNAL_SERVER_ERROR
  if (
    status >= 500 ||
    code === "INTERNAL_SERVER_ERROR" ||
    rawDetail.toLowerCase().includes("internal server error")
  ) {
    return {
      title: "Instabilidade temporária no servidor",
      detail:
        "Tivemos uma oscilação temporária ao conectar com a triagem médica. Seus dados continuam preenchidos. Por favor, tente novamente.",
      retryable: true,
    };
  }

  // Erros de Validação ou Regras de Domínio Clínicas (400, 422)
  return {
    title: "Atenção aos dados informados",
    detail: rawDetail,
    retryable: false,
  };
}
