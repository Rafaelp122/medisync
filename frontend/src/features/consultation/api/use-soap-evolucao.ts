import {
  type UseMutationOptions,
  type UseQueryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  obterEvolucaoSoapApiV1ConsultationsAtendimentoIdSoapGet,
  salvarEvolucaoSoapApiV1ConsultationsAtendimentoIdSoapPost,
} from "@/api/generated/sdk.gen";
import type { EvolucaoSoapResponse, RegistrarSoapRequest } from "@/api/generated/types.gen";
import { soapSchema } from "../schemas/consultation-schema";

export interface SalvarSoapParams extends RegistrarSoapRequest {
  token?: string;
}

/**
 * Hook headless de consulta às notas de evolução clínica SOAP do atendimento.
 * Regras: RF-07, US-09.
 */
export function useSoapEvolucao(
  atendimentoId: string,
  token?: string,
  options?: Omit<
    UseQueryOptions<EvolucaoSoapResponse | null, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery<EvolucaoSoapResponse | null, ProblemDetailsError>({
    queryKey: ["soap", atendimentoId],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await obterEvolucaoSoapApiV1ConsultationsAtendimentoIdSoapGet({
          client,
          path: {
            atendimento_id: atendimentoId,
          },
          headers,
          throwOnError: false,
        });

        // 404 é o estado natural inicial: a consulta foi iniciada e ainda não possui SOAP gravado
        if (response.status === 404) {
          return null;
        }

        if (response.error) {
          throw toProblemDetailsError(response.error);
        }

        return response.data ?? null;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(atendimentoId),
    retry: (failureCount, error) => {
      if (error?.status === 404) return false;
      return failureCount < 2;
    },
    ...options,
  });
}

/**
 * Hook headless de mutação para registrar ou atualizar notas SOAP no prontuário eletrônico.
 * Regras: RF-07, RN06 (Ato Médico), US-09, CFM nº 1.821/2007.
 */
export function useSalvarSoap(
  atendimentoId: string,
  options?: UseMutationOptions<EvolucaoSoapResponse, ProblemDetailsError, SalvarSoapParams>,
) {
  const queryClient = useQueryClient();

  return useMutation<EvolucaoSoapResponse, ProblemDetailsError, SalvarSoapParams>({
    mutationFn: async ({ token, ...body }: SalvarSoapParams) => {
      try {
        const validatedBody = soapSchema.parse(body);
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await salvarEvolucaoSoapApiV1ConsultationsAtendimentoIdSoapPost({
          client,
          path: {
            atendimento_id: atendimentoId,
          },
          body: validatedBody,
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, context) => {
      queryClient.invalidateQueries({ queryKey: ["soap", atendimentoId] });
      queryClient.invalidateQueries({ queryKey: ["prontuario", atendimentoId] });
      options?.onSuccess?.(data, variables, context);
    },
    ...options,
  });
}
