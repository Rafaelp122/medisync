import { z } from "zod";
import { zLoginRequest, zMfaVerificarLoginRequest } from "@/api/generated/zod.gen";

export const doctorLoginSchema = zLoginRequest.pick({ senha: true }).extend({
  crm: z.string().trim().min(3, "CRM deve conter pelo menos 3 dígitos").max(10, "CRM inválido"),
  uf: z.string().trim().length(2, "UF deve conter 2 letras").toUpperCase(),
  senha: z.string().min(1, "Senha obrigatória").max(128, "Senha muito longa"),
});

export type DoctorLoginFormData = z.infer<typeof doctorLoginSchema>;

export const managerLoginSchema = zLoginRequest.pick({ senha: true }).extend({
  email: z.string().trim().email("E-mail institucional inválido"),
  senha: z.string().min(1, "Senha obrigatória").max(128, "Senha muito longa"),
});

export type ManagerLoginFormData = z.infer<typeof managerLoginSchema>;

export const mfaVerifySchema = zMfaVerificarLoginRequest.extend({
  codigo: z
    .string()
    .length(6, "Código TOTP deve ter exatamente 6 dígitos")
    .regex(/^\d{6}$/, "O código deve conter apenas números"),
});

export type MfaVerifyFormData = z.infer<typeof mfaVerifySchema>;
