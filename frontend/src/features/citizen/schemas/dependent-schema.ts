import { z } from "zod";
import { zCriarDependenteRequest } from "@/api/generated/zod.gen";
import {
  formatarTelefoneE164,
  limparDigitos,
  validarCNS,
  validarCPF,
  validarTelefoneCelularBR,
} from "@/lib/validators";

/**
 * Schema Zod para cadastro de dependente legal/menor vinculado ao titular.
 * Deriva diretamente de zCriarDependenteRequest (Zero DTO Duplication - ADR-011).
 */
export const dependenteSchema = zCriarDependenteRequest
  .extend({
    grau_parentesco: z
      .string()
      .min(2, "Selecione ou informe o grau de parentesco")
      .max(32, "Grau de parentesco deve ter no máximo 32 caracteres"),
    nome_completo: z
      .string()
      .min(3, "Nome completo deve ter ao menos 3 caracteres")
      .max(255, "Nome completo deve ter no máximo 255 caracteres"),
    data_nascimento: z
      .string()
      .min(1, "Informe a data de nascimento do dependente")
      .refine(
        (val) => {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(val)) return false;
          const parsed = new Date(`${val}T00:00:00`);
          if (Number.isNaN(parsed.getTime())) return false;
          return parsed <= new Date();
        },
        { message: "Informe uma data de nascimento válida (não futura)" },
      ),
    cpf: z
      .string()
      .nullish()
      .transform((val) => {
        const digits = val ? limparDigitos(val) : "";
        return digits || null;
      }),
    cns: z
      .string()
      .nullish()
      .transform((val) => {
        const digits = val ? limparDigitos(val) : "";
        return digits || null;
      }),
    telefone: z
      .string()
      .nullish()
      .transform((val) => {
        const digits = val ? limparDigitos(val) : "";
        return digits ? formatarTelefoneE164(digits) : null;
      }),
  })
  .superRefine((data, ctx) => {
    if (data.cpf && !validarCPF(data.cpf)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "CPF inválido; verifique os dígitos informados",
        path: ["cpf"],
      });
    }
    if (data.cns && !validarCNS(data.cns)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "CNS inválido; informe um Cartão SUS válido",
        path: ["cns"],
      });
    }
    if (data.telefone && !validarTelefoneCelularBR(data.telefone)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Telefone inválido; informe DDD + 9 dígitos",
        path: ["telefone"],
      });
    }
  });

export type DependenteFormInput = z.input<typeof dependenteSchema>;
export type DependenteFormData = z.output<typeof dependenteSchema>;
