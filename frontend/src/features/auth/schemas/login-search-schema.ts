import { z } from "zod";

export const loginPerfilSchema = z.enum(["medico", "gestor", "cidadao"]);

export const loginSearchSchema = z.object({
  perfil: loginPerfilSchema.optional(),
});

export type LoginSearchParams = z.infer<typeof loginSearchSchema>;
