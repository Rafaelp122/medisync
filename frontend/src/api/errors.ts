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
