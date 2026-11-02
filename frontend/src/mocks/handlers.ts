import { HttpResponse, http } from "msw";
import {
  handleAdmitirPacienteApiV1FilaAdmissaoPost,
  handleEnrichmentFase2ApiV1OnboardingFase2Post,
  handleIntakeFase1ApiV1OnboardingFase1Post,
  handleLoginApiV1AuthLoginPost,
  handleObterPainelTelemetriaApiV1TelemetriaPainelGet,
  handleRequestOtpApiV1AuthPatientOtpRequestPost,
  handleVerifyOtpApiV1AuthPatientOtpVerifyPost,
} from "@/api/generated/msw.gen";
import { createPainelTelemetriaResponse } from "@/features/consultation/tests/fixtures";

import {
  createAdmissaoResponse,
  createEnrichmentFase2Response,
  createIntakeFase1Response,
  createViaCepRawResponse,
} from "@/features/onboarding/tests/fixtures";

export const defaultHandlers = [
  handleObterPainelTelemetriaApiV1TelemetriaPainelGet({
    body: createPainelTelemetriaResponse(),
  }),
  handleLoginApiV1AuthLoginPost({
    body: {
      access_token: "mock-jwt-token-medico",
      refresh_token: "mock-refresh-token-medico",
      token_type: "bearer",
      expires_in: 900,
      refresh_expires_in: 604800,
    },
  }),
  handleRequestOtpApiV1AuthPatientOtpRequestPost({
    body: {
      mensagem: "Código enviado com sucesso.",
      expira_em_segundos: 300,
      codigo_debug: "123456",
    },
  }),
  handleVerifyOtpApiV1AuthPatientOtpVerifyPost({
    body: {
      access_token: "mock-jwt-token-paciente",
      token_type: "bearer",
      expires_in: 3600,
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      role: "PACIENTE",
    },
  }),
  handleIntakeFase1ApiV1OnboardingFase1Post({
    status: 201,
    body: createIntakeFase1Response(),
  }),
  handleAdmitirPacienteApiV1FilaAdmissaoPost({
    status: 201,
    body: createAdmissaoResponse(),
  }),
  handleEnrichmentFase2ApiV1OnboardingFase2Post({
    status: 200,
    body: createEnrichmentFase2Response(),
  }),
  http.get("https://viacep.com.br/ws/:cep/json/", ({ params }) => {
    const cep = String(params.cep).replace(/\D/g, "");
    if (cep === "01310100") {
      return HttpResponse.json(createViaCepRawResponse());
    }
    if (cep === "00000000" || cep === "99999999") {
      return HttpResponse.json({ erro: "true" });
    }
    return HttpResponse.json(
      createViaCepRawResponse({
        cep: `${cep.slice(0, 5)}-${cep.slice(5)}`,
        logradouro: "Rua das Flores",
        bairro: "Centro",
      }),
    );
  }),
];
