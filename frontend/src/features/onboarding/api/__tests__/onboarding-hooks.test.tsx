import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type React from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import {
  createAdmissaoResponse,
  createEnrichmentFase2FormData,
  createEnrichmentFase2Response,
  createIntakeFase1FormData,
  createIntakeFase1Response,
  createViaCepEndereco,
  MOCK_PACIENTE_ID,
  MOCK_TCLE_HASH,
} from "../../tests/fixtures";
import { useAdmitirPaciente } from "../use-admitir-paciente";
import { useEnrichmentFase2 } from "../use-enrichment-fase2";
import { useIntakeFase1 } from "../use-intake-fase1";
import { buscarEnderecoPorCep, useViaCep } from "../use-via-cep";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});

function TestWrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("Hooks de Onboarding Clínico", () => {
  beforeEach(() => {
    queryClient.clear();
  });
  it("HK-01: useIntakeFase1 executa chamada com sucesso", async () => {
    server.use(
      http.post("*/api/v1/onboarding/fase-1", () => {
        return HttpResponse.json(
          createIntakeFase1Response({
            token: "fake-jwt-intake-token",
            mensagem: "Acolhimento realizado",
          }),
          { status: 201 },
        );
      }),
    );

    const { result } = renderHook(() => useIntakeFase1(), { wrapper: TestWrapper });

    result.current.mutate(
      createIntakeFase1FormData({
        telefone: "+5511987654321",
        queixa_principal: "Febre e dor",
      }),
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.token).toBe("fake-jwt-intake-token");
    expect(result.current.data?.paciente_id).toBe(MOCK_PACIENTE_ID);
  });

  it("HK-02: useIntakeFase1 trata erro RFC 7807 (422)", async () => {
    server.use(
      http.post("*/api/v1/onboarding/fase-1", () => {
        return HttpResponse.json(
          {
            status: 422,
            title: "Validation Error",
            detail: "Dados de acolhimento inválidos",
            code: "VALIDATION_ERROR",
          },
          { status: 422 },
        );
      }),
    );

    const { result } = renderHook(() => useIntakeFase1(), { wrapper: TestWrapper });

    result.current.mutate({
      nome_completo: "Juliana Silva",
      data_nascimento: "1990-05-15",
      telefone: "+5511987654321",
      queixa_principal: "Febre e dor",
      tcle_hash: "a".repeat(64),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.detail).toBe("Dados de acolhimento inválidos");
  });

  it("HK-03: useAdmitirPaciente executa chamada de admissão e triagem", async () => {
    server.use(
      http.post("*/api/v1/fila/admissao", () => {
        return HttpResponse.json(createAdmissaoResponse(), { status: 201 });
      }),
    );

    const { result } = renderHook(() => useAdmitirPaciente(), { wrapper: TestWrapper });

    result.current.mutate({
      body: {
        paciente_id: MOCK_PACIENTE_ID,
        queixa_principal: "Febre e tosse",
        escala_dor: 4,
        tcle_hash: MOCK_TCLE_HASH,
      },
      token: "bearer-token-123",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.prioridade_clinica).toBe(3);
    expect(result.current.data?.status_atendimento).toBe("TRIADO_AGUARDANDO_ELEGIBILIDADE");
  });

  it("HK-04: useAdmitirPaciente detecta rejeição SAMU 192", async () => {
    server.use(
      http.post("*/api/v1/fila/admissao", () => {
        return HttpResponse.json(
          {
            status: 422,
            title: "Emergência Médica Crítica — Acionamento SAMU 192",
            detail: "Emergência médica crítica detectada (Nível 1). Acione o SAMU 192.",
            code: "EMERGENCIA_CRITICA_SAMU_192",
          },
          { status: 422 },
        );
      }),
    );

    const { result } = renderHook(() => useAdmitirPaciente(), { wrapper: TestWrapper });

    result.current.mutate({
      body: {
        paciente_id: MOCK_PACIENTE_ID,
        queixa_principal: "Parada cardiaca",
        escala_dor: 10,
        tcle_hash: MOCK_TCLE_HASH,
      },
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.code).toBe("EMERGENCIA_CRITICA_SAMU_192");
  });

  it("HK-05: useEnrichmentFase2 envia dados complementares com sucesso", async () => {
    server.use(
      http.post("*/api/v1/onboarding/fase-2", () => {
        return HttpResponse.json(createEnrichmentFase2Response(), { status: 200 });
      }),
    );

    const { result } = renderHook(() => useEnrichmentFase2(), { wrapper: TestWrapper });

    result.current.mutate({
      body: createEnrichmentFase2FormData(),
      token: "token-fase1",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.cep).toBe("01310100");
  });

  it("HK-06: buscarEnderecoPorCep consulta ViaCEP e retorna dados mapeados", async () => {
    server.use(
      http.get("https://viacep.com.br/ws/01310100/json/", () => {
        return HttpResponse.json({
          cep: "01310-100",
          logradouro: "Avenida Paulista",
          bairro: "Bela Vista",
          localidade: "São Paulo",
          uf: "SP",
        });
      }),
    );

    const res = await buscarEnderecoPorCep("01310-100");
    expect(res).toEqual(createViaCepEndereco());
  });

  it("HK-07: buscarEnderecoPorCep retorna null para CEP com erro: true", async () => {
    server.use(
      http.get("https://viacep.com.br/ws/99999999/json/", () => {
        return HttpResponse.json({ erro: "true" });
      }),
    );

    const res = await buscarEnderecoPorCep("99999-999");
    expect(res).toBeNull();
  });

  it("HK-08: useViaCep atualiza estado automaticamente para CEP de 8 dígitos", async () => {
    server.use(
      http.get("https://viacep.com.br/ws/01310100/json/", () => {
        return HttpResponse.json({
          cep: "01310-100",
          logradouro: "Avenida Paulista",
          bairro: "Bela Vista",
          localidade: "São Paulo",
          uf: "SP",
        });
      }),
    );

    const { result } = renderHook(() => useViaCep("01310-100"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.endereco).toEqual({
      logradouro: "Avenida Paulista",
      bairro: "Bela Vista",
      cidade: "São Paulo",
      estado: "SP",
    });
  });
});
