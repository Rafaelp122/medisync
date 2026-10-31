import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { intakeFase1ApiV1OnboardingFase1Post } from "@/api/generated/sdk.gen";
import type {
  Fase1Request,
  IntakeFase1ApiV1OnboardingFase1PostResponse,
} from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para Acolhimento Clínico Inicial (Fase 1).
 * Regras canônicas: RF-01, US-01 e ADR-011.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function useIntakeFase1(
  options?: UseMutationOptions<
    IntakeFase1ApiV1OnboardingFase1PostResponse,
    ProblemDetailsError,
    Fase1Request
  >,
) {
  return useMutation<
    IntakeFase1ApiV1OnboardingFase1PostResponse,
    ProblemDetailsError,
    Fase1Request
  >({
    mutationFn: async (payload: Fase1Request) => {
      try {
        const response = await intakeFase1ApiV1OnboardingFase1Post({
          client,
          body: payload,
          headers: {
            "X-Tenant-ID": getActiveTenantId(),
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
