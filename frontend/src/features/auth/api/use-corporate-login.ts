import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId, getTenantHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { loginApiV1AuthLoginPost } from "@/api/generated/sdk.gen";
import type { LoginRequest, TokenResponse } from "@/api/generated/types.gen";

export function useCorporateLogin(
  options?: UseMutationOptions<TokenResponse, ProblemDetailsError, LoginRequest>,
) {
  return useMutation<TokenResponse, ProblemDetailsError, LoginRequest>({
    mutationFn: async (body: LoginRequest) => {
      try {
        const activeTenant = getActiveTenantId();
        const parsedTenant = activeTenant ? Number.parseInt(activeTenant, 10) : Number.NaN;
        const resolvedOrganizacaoId =
          body.organizacao_id ??
          (Number.isFinite(parsedTenant) && parsedTenant > 0 ? parsedTenant : undefined);

        const response = await loginApiV1AuthLoginPost({
          client,
          headers: getTenantHeaders(),
          body: {
            ...body,
            ...(resolvedOrganizacaoId !== undefined
              ? { organizacao_id: resolvedOrganizacaoId }
              : {}),
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
