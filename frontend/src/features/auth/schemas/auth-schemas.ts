import { z } from "zod";
import { validarCNS, validarCPF } from "@/lib/validators";

export const cadsusAuthSchema = z.object({
  cpf: z
    .string()
    .min(11, "CPF deve conter 11 dígitos")
    .refine((val) => validarCPF(val), {
      message: "CPF inválido. Verifique os dígitos informados.",
    }),
  cns: z
    .string()
    .optional()
    .refine(
      (val) => {
        if (!val?.trim()) return true;
        return validarCNS(val);
      },
      { message: "Cartão Nacional de Saúde (CNS) inválido." },
    ),
  dataNascimento: z
    .string()
    .min(10, "Data de nascimento obrigatória (AAAA-MM-DD)")
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Formato de data inválido (AAAA-MM-DD)"),
  nomeMae: z
    .string()
    .min(3, "Nome da mãe deve ter pelo menos 3 caracteres")
    .max(200, "Nome da mãe muito longo"),
});

export type CadsusAuthFormData = z.infer<typeof cadsusAuthSchema>;

export const doctorLoginSchema = z.object({
  crm: z.string().min(3, "CRM deve conter pelo menos 3 dígitos").max(10, "CRM inválido"),
  uf: z.string().length(2, "UF deve conter 2 letras").toUpperCase(),
  senha: z.string().min(1, "Senha obrigatória"),
});

export type DoctorLoginFormData = z.infer<typeof doctorLoginSchema>;

export const managerLoginSchema = z.object({
  email: z.string().email("E-mail institucional inválido"),
  senha: z.string().min(1, "Senha obrigatória"),
});

export type ManagerLoginFormData = z.infer<typeof managerLoginSchema>;

export const mfaVerifySchema = z.object({
  codigo: z
    .string()
    .length(6, "Código TOTP deve ter exatamente 6 dígitos")
    .regex(/^\d{6}$/, "O código deve conter apenas números"),
});

export type MfaVerifyFormData = z.infer<typeof mfaVerifySchema>;
