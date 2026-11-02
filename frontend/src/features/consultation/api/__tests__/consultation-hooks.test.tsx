import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type React from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { useAssinarDocumento } from "../use-assinar-documento";
import { useChamarProximo } from "../use-chamar-proximo";
import { useEmitirDocumento } from "../use-emitir-documento";
import { useFinalizarConsulta } from "../use-finalizar-consulta";
import { useLiveKitToken } from "../use-livekit-token";
import { usePrescricaoValidator } from "../use-prescricao-validator";
import { useProntuario } from "../use-prontuario";
import { useSalvarSoap } from "../use-soap-evolucao";
import { useTmaStatus } from "../use-tma-status";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});

function TestWrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const MOCK_ATENDIMENTO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d";
const MOCK_MEDICO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e";
const MOCK_DOC_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2f";

describe("Consultation API Hooks (US-09, US-10, RF-07, RN06)", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("HK-CONS-01: useChamarProximo adquire paciente da fila virtual", async () => {
    server.use(
      http.post("*/api/v1/fila/chamar-proximo", () => {
        return HttpResponse.json({
          alocado: true,
          atendimento_id: MOCK_ATENDIMENTO_ID,
          paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          medico_id: MOCK_MEDICO_ID,
          prioridade_clinica: 2,
          status: "EM_ATENDIMENTO",
          chamada_iniciada_em: "2026-11-01T12:00:00Z",
          ttl_segundos: 900,
        });
      }),
    );

    const { result } = renderHook(() => useChamarProximo(), { wrapper: TestWrapper });
    result.current.mutate({});

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.alocado).toBe(true);
    expect(result.current.data?.atendimento_id).toBe(MOCK_ATENDIMENTO_ID);
  });

  it("HK-CONS-02: useLiveKitToken emite token WebRTC SFU assinado", async () => {
    server.use(
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/livekit/token`, () => {
        return HttpResponse.json({
          token: "fake-jwt-livekit-token",
          room_name: "org_1_atend_123",
          participant_identity: `medico_${MOCK_MEDICO_ID}`,
          server_url: "wss://livekit.medisync.local",
          expires_in: 3600,
        });
      }),
    );

    const { result } = renderHook(() => useLiveKitToken(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });
    result.current.mutate({
      organizacao_id: 1,
      participant_id: MOCK_MEDICO_ID,
      role: "medico",
      participant_name: "Dr. Eduardo Rocha",
      is_publisher: true,
      ttl_seconds: 3600,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.token).toBe("fake-jwt-livekit-token");
    expect(result.current.data?.server_url).toBe("wss://livekit.medisync.local");
  });

  it("HK-CONS-03: useProntuario carrega prontuário e histórico clínico", async () => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        return HttpResponse.json({
          atendimento_id: MOCK_ATENDIMENTO_ID,
          is_finalizado: false,
          evolucao: null,
          documentos: [],
        });
      }),
    );

    const { result } = renderHook(() => useProntuario(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.atendimento_id).toBe(MOCK_ATENDIMENTO_ID);
    expect(result.current.data?.is_finalizado).toBe(false);
  });

  it("HK-CONS-04: useSalvarSoap persiste evolução clínica SOAP", async () => {
    server.use(
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/soap`, () => {
        return HttpResponse.json({
          id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b30",
          atendimento_id: MOCK_ATENDIMENTO_ID,
          organizacao_id: 1,
          medico_id: MOCK_MEDICO_ID,
          anamnese: "Paciente com dor de garganta.",
          exame_fisico_virtual: "Orofaringe hiperemiada.",
          cid10_principal: "J03.0",
          conduta: "Prescrito Amoxicilina.",
          registrado_em: "2026-11-01T12:05:00Z",
          is_finalizado: false,
        });
      }),
    );

    const { result } = renderHook(() => useSalvarSoap(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });
    result.current.mutate({
      anamnese: "Paciente com dor de garganta.",
      exame_fisico_virtual: "Orofaringe hiperemiada.",
      cid10_principal: "J03.0",
      conduta: "Prescrito Amoxicilina.",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.cid10_principal).toBe("J03.0");
  });

  it("HK-CONS-05: usePrescricaoValidator valida medicamento contra Portaria 344/98", async () => {
    server.use(
      http.post(
        `*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prescriptions/validate`,
        async ({ request }) => {
          const body = (await request.json()) as { medicamento: string };
          if (body.medicamento.toLowerCase().includes("zolpidem")) {
            return HttpResponse.json(
              {
                status: 422,
                title: "Prescrição Proibida em Telemedicina",
                detail:
                  "O medicamento 'Zolpidem' exige Notificação de Receita B e não pode ser emitido digitalmente.",
                code: "PRESCRICAO_FISICA_OBRIGATORIA",
              },
              { status: 422 },
            );
          }
          return HttpResponse.json({
            status: "PERMITIDO",
            medicamento: body.medicamento,
            mensagem: "Substância autorizada para prescrição digital em telemedicina.",
          });
        },
      ),
    );

    const { result } = renderHook(() => usePrescricaoValidator(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });

    // Teste substância autorizada
    result.current.mutate({ medicamento: "Amoxicilina 500mg" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("PERMITIDO");

    // Teste substância proibida
    result.current.mutate({ medicamento: "Zolpidem 10mg" });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.code).toBe("PRESCRICAO_FISICA_OBRIGATORIA");
  });

  it("HK-CONS-06: useEmitirDocumento e useAssinarDocumento concluem fluxo de receita ICP-Brasil", async () => {
    server.use(
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents`, () => {
        return HttpResponse.json(
          {
            id: MOCK_DOC_ID,
            atendimento_id: MOCK_ATENDIMENTO_ID,
            organizacao_id: 1,
            medico_id: MOCK_MEDICO_ID,
            tipo_documento: "RECEITA_SIMPLES",
            chave_s3: "prescricoes/doc.pdf",
            is_finalizado: false,
            itens: [],
          },
          { status: 201 },
        );
      }),
      http.post(
        `*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents/${MOCK_DOC_ID}/sign`,
        () => {
          return HttpResponse.json({
            documento_id: MOCK_DOC_ID,
            tipo_documento: "RECEITA_SIMPLES",
            sha256_hash: "abcd1234ef5678",
            assinado_em: "2026-11-01T12:10:00Z",
            tamanho_bytes: 10240,
            status: "ASSINADO",
          });
        },
      ),
    );

    const { result: emitirResult } = renderHook(() => useEmitirDocumento(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });
    emitirResult.current.mutate({
      tipo_documento: "RECEITA_SIMPLES",
      itens: [
        {
          medicamento: "Amoxicilina 500mg",
          dosagem: "500mg",
          posologia: "1 cp 8/8h",
          controle_especial: false,
        },
      ],
    });

    await waitFor(() => expect(emitirResult.current.isSuccess).toBe(true));
    expect(emitirResult.current.data?.id).toBe(MOCK_DOC_ID);

    const { result: assinarResult } = renderHook(() => useAssinarDocumento(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });
    assinarResult.current.mutate({
      documento_id: MOCK_DOC_ID,
      payload: {
        token: "psc-token-123",
        provider: "birdid",
      },
    });

    await waitFor(() => expect(assinarResult.current.isSuccess).toBe(true));
    expect(assinarResult.current.data?.status).toBe("ASSINADO");
  });

  it("HK-CONS-07: useTmaStatus e useFinalizarConsulta respeitam imutabilidade e telemetria (RN06)", async () => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/tma-status`, () => {
        return HttpResponse.json({
          atendimento_id: MOCK_ATENDIMENTO_ID,
          tempo_decorrido_segundos: 950,
          tma_planejado_segundos: 900,
          excedeu_tma: true,
          aviso_visual: "TMA excedido em 50s. Atendimento preservado sob RN06.",
        });
      }),
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/finalize`, () => {
        return HttpResponse.json({
          status: "FINALIZADO",
          atendimento_id: MOCK_ATENDIMENTO_ID,
          is_finalizado: true,
          mensagem: "Consulta finalizada com sucesso.",
        });
      }),
    );

    const { result: tmaResult } = renderHook(() => useTmaStatus(MOCK_ATENDIMENTO_ID), {
      wrapper: TestWrapper,
    });

    await waitFor(() => expect(tmaResult.current.isSuccess).toBe(true));
    expect(tmaResult.current.data?.excedeu_tma).toBe(true);

    const { result: finalizarResult } = renderHook(
      () => useFinalizarConsulta(MOCK_ATENDIMENTO_ID),
      { wrapper: TestWrapper },
    );
    finalizarResult.current.mutate({});

    await waitFor(() => expect(finalizarResult.current.isSuccess).toBe(true));
    expect(finalizarResult.current.data?.is_finalizado).toBe(true);
  });
});
