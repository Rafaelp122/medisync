import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { postAuthPacienteCadsus } from "@/api/generated/sdk.gen";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { limparDigitos } from "@/lib/validators";
import type { CadsusAuthFormData } from "../schemas/auth-schemas";

export function useCadsusLogin(
  options?: UseMutationOptions<VerificarOtpResponse, ProblemDetailsError, CadsusAuthFormData>,
) {
  return useMutation<VerificarOtpResponse, ProblemDetailsError, CadsusAuthFormData>({
    mutationFn: async (formData: CadsusAuthFormData) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };

        const response = await postAuthPacienteCadsus({
          client,
          headers,
          body: {
            cpf: limparDigitos(formData.cpf),
            cns: formData.cns ? limparDigitos(formData.cns) : null,
            data_nascimento: formData.dataNascimento,
            nome_mae: formData.nomeMae?.trim() || null,
          },
          throwOnError: true,
        });

        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
