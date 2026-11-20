import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { loginApiV1AuthLoginPost } from "@/api/generated/sdk.gen";
import type { LoginRequest, TokenResponse } from "@/api/generated/types.gen";

export function useCorporateLogin(
  options?: UseMutationOptions<TokenResponse, ProblemDetailsError, LoginRequest>,
) {
  return useMutation<TokenResponse, ProblemDetailsError, LoginRequest>({
    mutationFn: async (body: LoginRequest) => {
      try {
        const response = await loginApiV1AuthLoginPost({
          client,
          body,
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
