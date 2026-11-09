import { z } from "zod";

export const entryModeSchema = z.enum([
  "acolhimento",
  "otp",
  "login",
  "gestor",
  "manager",
  "medico",
  "doctor",
  "cadsus",
]);

export const entryPerfilSchema = z.enum(["cidadao", "medico", "gestor"]);

export const entrySearchSchema = z.object({
  mode: entryModeSchema.optional(),
  perfil: entryPerfilSchema.optional(),
});

export type EntrySearchParams = z.infer<typeof entrySearchSchema>;
