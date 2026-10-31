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
      });

      expect(isProblemDetailsError(err)).toBe(true);
      expect(err.status).toBe(404);
      expect(err.detail).toBe("Recurso não existe");
      expect(err.code).toBe("NOT_FOUND");
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

    it("deve tratar 500 como instabilidade temporária no servidor", () => {
      const err500 = { status: 500, detail: "Internal Server Error" };
      const humanized = getHumanizedErrorMessage(err500);

      expect(humanized.title).toBe("Instabilidade temporária no servidor");
      expect(humanized.detail).toContain("oscilação temporária");
      expect(humanized.retryable).toBe(true);
    });

    it("deve tratar falha de rede / Failed to fetch", () => {
      const errNetwork = new Error("Failed to fetch");
      const humanized = getHumanizedErrorMessage(errNetwork);

      expect(humanized.title).toBe("Falha de conexão com a internet");
      expect(humanized.retryable).toBe(true);
    });

    it("deve tratar erro de TENANT_INVALIDO", () => {
      const errTenant = { code: "TENANT_INVALIDO", detail: "Tenant não informado" };
      const humanized = getHumanizedErrorMessage(errTenant);

      expect(humanized.title).toBe("Identificação da unidade de saúde");
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
