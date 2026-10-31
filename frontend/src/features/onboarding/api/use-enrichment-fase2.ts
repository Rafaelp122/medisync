import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { enrichmentFase2ApiV1OnboardingFase2Post } from "@/api/generated/sdk.gen";
import type {
  EnrichmentFase2ApiV1OnboardingFase2PostResponse,
  Fase2Request,
} from "@/api/generated/types.gen";

export interface EnrichmentFase2Params {
  body: Fase2Request;
  token?: string;
}

/**
 * Hook headless de mutação para Enriquecimento Cadastral Regulatório CFM 1.821/2007 (Fase 2).
 * Regras canônicas: RF-02, US-03 e ADR-011.
 * @see docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
 */
export function useEnrichmentFase2(
  options?: UseMutationOptions<
    EnrichmentFase2ApiV1OnboardingFase2PostResponse,
    ProblemDetailsError,
    EnrichmentFase2Params
  >,
) {
  return useMutation<
    EnrichmentFase2ApiV1OnboardingFase2PostResponse,
    ProblemDetailsError,
    EnrichmentFase2Params
  >({
    mutationFn: async ({ body, token }: EnrichmentFase2Params) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await enrichmentFase2ApiV1OnboardingFase2Post({
          client,
          body,
          headers,
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
