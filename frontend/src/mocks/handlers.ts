import {
  handleRequestOtpApiV1AuthPatientOtpRequestPost,
  handleVerifyOtpApiV1AuthPatientOtpVerifyPost,
} from "@/api/generated/msw.gen";

export const defaultHandlers = [
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
      paciente_id: "00000000-0000-0000-0000-000000000001",
      role: "PACIENTE",
    },
  }),
];
