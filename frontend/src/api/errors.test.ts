import { describe, expect, it } from "vitest";
import {
  extractProblemDetail,
  extractProblemStatus,
  getHumanizedErrorMessage,
  isProblemDetailsError,
  ProblemDetailsError,
  toProblemDetailsError,
} from "./errors";

describe("api/errors.ts", () => {
  describe("ProblemDetailsError & helpers", () => {
    it("deve instanciar ProblemDetailsError com status e campos RFC 7807", () => {
      const err = new ProblemDetailsError({
        status: 404,
        title: "Não Encontrado",
        detail: "Recurso não existe",
        code: "NOT_FOUND",
        request_id: "req-123",
        invalid_params: [{ name: "cpf", reason: "Dígito verificador inválido" }],
      });

      expect(isProblemDetailsError(err)).toBe(true);
      expect(err.status).toBe(404);
      expect(err.detail).toBe("Recurso não existe");
      expect(err.code).toBe("NOT_FOUND");
      expect(err.requestId).toBe("req-123");
      expect(err.invalidParams).toEqual([{ name: "cpf", reason: "Dígito verificador inválido" }]);
    });

    it("toProblemDetailsError deve converter DOMException TimeoutError para status 504 TIMEOUT", () => {
      const timeoutErr = new DOMException(
        "The operation was aborted due to timeout",
        "TimeoutError",
      );
      const problem = toProblemDetailsError(timeoutErr);

      expect(problem.status).toBe(504);
      expect(problem.code).toBe("TIMEOUT");
    });

    it("toProblemDetailsError deve converter objetos arbitrários e strings", () => {
      const fromObj = toProblemDetailsError({ status: 400, detail: "Parâmetro inválido" });
      expect(fromObj.status).toBe(400);
      expect(fromObj.detail).toBe("Parâmetro inválido");

      const fromStr = toProblemDetailsError("Erro de conexão", 503);
      expect(fromStr.status).toBe(503);
      expect(fromStr.detail).toBe("Erro de conexão");

      const identity = toProblemDetailsError(fromObj);
      expect(identity).toBe(fromObj);
    });

    it("extractProblemDetail e extractProblemStatus extraem valores com fallback seguro", () => {
      expect(extractProblemStatus(null, 500)).toBe(500);
      expect(extractProblemStatus({ status: 422 })).toBe(422);
      expect(extractProblemDetail(null, "fallback")).toBe("fallback");
      expect(extractProblemDetail({ detail: "detalhe" })).toBe("detalhe");
      expect(extractProblemDetail("string error")).toBe("string error");
    });
  });

  describe("getHumanizedErrorMessage", () => {
    it("deve priorizar 504 Gateway Timeout sobre erro 500 genérico", () => {
      const err504 = { status: 504, detail: "Gateway Timeout" };
      const humanized = getHumanizedErrorMessage(err504);

      expect(humanized.title).toBe("Tempo de resposta esgotado");
      expect(humanized.detail).toContain("demorou mais do que o esperado");
      expect(humanized.retryable).toBe(true);
    });

    it("deve tratar código TIMEOUT ou mensagem de timeout como erro recuperável", () => {
      const errTimeout = { code: "TIMEOUT", detail: "Request timeout" };
      const humanized = getHumanizedErrorMessage(errTimeout);

      expect(humanized.title).toBe("Tempo de resposta esgotado");
      expect(humanized.retryable).toBe(true);
    });

    it("deve tratar 500 e 503 sem mencionar contexto específico de triagem médica", () => {
      const err500 = { status: 500, detail: "Internal Server Error" };
      const humanized500 = getHumanizedErrorMessage(err500);

      expect(humanized500.title).toBe("Instabilidade temporária no servidor");
      expect(humanized500.detail).toContain("oscilação temporária");
      expect(humanized500.detail.toLowerCase()).not.toContain("triagem médica");
      expect(humanized500.retryable).toBe(true);

      const err503 = { status: 503, detail: "Service Unavailable" };
      const humanized503 = getHumanizedErrorMessage(err503);
      expect(humanized503.detail.toLowerCase()).not.toContain("triagem médica");
      expect(humanized503.retryable).toBe(true);
    });

    it("deve distinguir erro 403 acesso negado e 429 excesso de requisições", () => {
      const err403 = getHumanizedErrorMessage({ status: 403, detail: "Perfil sem permissão" });
      expect(err403.title).toBe("Acesso não autorizado");
      expect(err403.detail).toBe("Perfil sem permissão");
      expect(err403.retryable).toBe(false);

      const err429 = getHumanizedErrorMessage({ status: 429, detail: "Rate limit" });
      expect(err429.title).toBe("Muitas tentativas em sequência");
      expect(err429.retryable).toBe(true);
    });

    it("deve tratar falha de rede / Failed to fetch", () => {
      const errNetwork = new Error("Failed to fetch");
      const humanized = getHumanizedErrorMessage(errNetwork);

      expect(humanized.title).toBe("Falha de conexão com a internet");
      expect(humanized.retryable).toBe(true);
    });

    it("deve tratar erro de validação 422 como não recuperável automaticamente", () => {
      const err422 = {
        status: 422,
        detail: "Telefone deve conter DDD e 9 dígitos.",
        code: "VALIDATION_ERROR",
      };
      const humanized = getHumanizedErrorMessage(err422);

      expect(humanized.title).toBe("Atenção aos dados informados");
      expect(humanized.detail).toBe("Telefone deve conter DDD e 9 dígitos.");
      expect(humanized.retryable).toBe(false);
    });
  });
});
