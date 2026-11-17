import {
  type UseMutationOptions,
  type UseQueryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { client, getSessionQueryScope, resolveExplicitAuthHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  cadastrarDependenteApiV1PacientesIdDependentesPost,
  listarDependentesApiV1PacientesIdDependentesGet,
} from "@/api/generated/sdk.gen";
import type {
  CriarDependenteRequest,
  DependenteDetalheResponse,
  DependenteResponse,
} from "@/api/generated/types.gen";

/**
 * Hook headless para listar dependentes vinculados ao paciente titular.
 */
export function useDependents(
  pacienteId: string,
  token?: string,
  options?: Omit<
    UseQueryOptions<DependenteDetalheResponse[], ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope(token);
  return useQuery<DependenteDetalheResponse[], ProblemDetailsError>({
    queryKey: ["citizen", "dependents", pacienteId, scopeKey],
    queryFn: async () => {
      try {
        const response = await listarDependentesApiV1PacientesIdDependentesGet({
          client,
          path: { id: pacienteId },
          headers: resolveExplicitAuthHeaders(token),
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(pacienteId),
    ...options,
  });
}

export interface CreateDependentParams {
  body: CriarDependenteRequest;
  token?: string;
}

/**
 * Hook headless para cadastrar ou vincular dependente legal/menor ao paciente titular.
 */
export function useCreateDependent(
  pacienteId: string,
  options?: UseMutationOptions<DependenteResponse, ProblemDetailsError, CreateDependentParams>,
) {
  const queryClient = useQueryClient();

  return useMutation<DependenteResponse, ProblemDetailsError, CreateDependentParams>({
    mutationFn: async ({ body, token }: CreateDependentParams) => {
      try {
        const response = await cadastrarDependenteApiV1PacientesIdDependentesPost({
          client,
          path: { id: pacienteId },
          body,
          headers: resolveExplicitAuthHeaders(token),
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: ["citizen", "dependents", pacienteId] });
      await options?.onSuccess?.(...args);
    },
    ...options,
  });
}
