import {
  type UseMutationOptions,
  type UseQueryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  cadastrarDisponibilidadeApiV1SchedulingDisponibilidadesPost,
  iniciarAtendimentoAgendadoApiV1SchedulingAgendamentosAgendamentoIdIniciarPost,
  listarAgendaDiaApiV1SchedulingAgendaDiaGet,
} from "@/api/generated/sdk.gen";
import type {
  AgendamentoResponse,
  CriarDisponibilidadeRequest,
  DisponibilidadeResponse,
} from "@/api/generated/types.gen";

export interface UseAgendaDiaParams {
  data?: string;
  dataInicio?: string;
  dataFim?: string;
  enabled?: boolean;
}

/**
 * Hook headless para listar a agenda de agendamentos do profissional autenticado no período.
 */
export function useAgendaDia(
  { data, dataInicio, dataFim, enabled = true }: UseAgendaDiaParams = {},
  options?: Partial<UseQueryOptions<AgendamentoResponse[], ProblemDetailsError>>,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<AgendamentoResponse[], ProblemDetailsError>({
    queryKey: [
      "scheduling",
      "agenda-dia",
      scopeKey,
      data ?? null,
      dataInicio ?? null,
      dataFim ?? null,
    ],
    queryFn: async () => {
      try {
        const response = await listarAgendaDiaApiV1SchedulingAgendaDiaGet({
          client,
          query: {
            ...(data ? { data } : {}),
            ...(dataInicio ? { data_inicio: dataInicio } : {}),
            ...(dataFim ? { data_fim: dataFim } : {}),
          },
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled,
    ...options,
  });
}

export interface CadastrarDisponibilidadeParams {
  body: CriarDisponibilidadeRequest;
}

/**
 * Hook headless de mutação para cadastrar janela semanal recorrente de disponibilidade do profissional.
 */
export function useCadastrarDisponibilidade(
  options?: UseMutationOptions<
    DisponibilidadeResponse,
    ProblemDetailsError,
    CadastrarDisponibilidadeParams
  >,
) {
  const queryClient = useQueryClient();

  return useMutation<DisponibilidadeResponse, ProblemDetailsError, CadastrarDisponibilidadeParams>({
    ...options,
    mutationFn: async ({ body }: CadastrarDisponibilidadeParams) => {
      try {
        const response = await cadastrarDisponibilidadeApiV1SchedulingDisponibilidadesPost({
          client,
          body,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({ queryKey: ["scheduling", "agenda-dia"] });
      void queryClient.invalidateQueries({ queryKey: ["scheduling", "slots"] });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}

export interface IniciarAtendimentoAgendadoParams {
  agendamentoId: string;
  atendimentoId?: string | null;
}

/**
 * Hook headless de mutação para iniciar teleconsulta a partir de um agendamento programado.
 */
export function useIniciarAtendimentoAgendado(
  options?: UseMutationOptions<
    AgendamentoResponse,
    ProblemDetailsError,
    IniciarAtendimentoAgendadoParams
  >,
) {
  const queryClient = useQueryClient();

  return useMutation<AgendamentoResponse, ProblemDetailsError, IniciarAtendimentoAgendadoParams>({
    ...options,
    mutationFn: async ({ agendamentoId, atendimentoId }: IniciarAtendimentoAgendadoParams) => {
      try {
        const response =
          await iniciarAtendimentoAgendadoApiV1SchedulingAgendamentosAgendamentoIdIniciarPost({
            client,
            path: { agendamento_id: agendamentoId },
            body: atendimentoId !== undefined ? { atendimento_id: atendimentoId } : null,
            throwOnError: true,
          });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({ queryKey: ["scheduling", "agenda-dia"] });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}
