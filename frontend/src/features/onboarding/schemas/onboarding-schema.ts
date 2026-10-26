import { z } from "zod";
import { zSolicitarOtpRequest, zVerificarOtpRequest } from "@/api/generated/zod.gen";
import { formatarTelefoneE164, validarTelefoneCelularBR } from "@/lib/validators";

/**
 * Schema Zod de validação para solicitação de OTP com validação estrita de telefone brasileiro.
 * Regras canônicas: RF-01, US-02 (§5.1) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export const solicitarOtpSchema = zSolicitarOtpRequest.extend({
  telefone: z
    .string()
    .refine((val) => validarTelefoneCelularBR(val), {
      message: "Telefone inválido; informe DDD + 9 dígitos",
    })
    .transform((val) => formatarTelefoneE164(val)),
});

/**
 * Schema Zod de validação para verificação de OTP com 6 dígitos numéricos.
 * Regras canônicas: RF-01, US-02 (§5.1) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export const verificarOtpSchema = zVerificarOtpRequest.extend({
  codigo: z.string().regex(/^\d{6}$/, "O código deve conter exatamente 6 dígitos numéricos"),
});

export type SolicitarOtpFormData = z.infer<typeof solicitarOtpSchema>;
export type VerificarOtpFormData = z.infer<typeof verificarOtpSchema>;
