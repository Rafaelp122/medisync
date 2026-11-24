import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import type { PosicaoFilaResponse } from "@/api/generated/types.gen";
import { settings } from "@/config/settings";
import type { StoredPatientSession } from "@/lib/session-storage";
import { useCancelarFila } from "../api/use-cancelar-fila";
import { usePosicaoFila } from "../api/use-posicao-fila";
import { type IncomingCallEvent, useQueueSocket } from "../api/use-queue-socket";

export type StatusAtendimento = string;

const TERMINAL_QUEUE_STATUSES = new Set([
  "PACIENTE_AUSENTE",
  "CANCELADO_PACIENTE",
  "CONCLUIDO",
  "CANCELADO",
]);

export interface ChamadaAtivaState {
  sala: string;
  chamadaIniciadaEm: string;
  ttlSegundos: number;
}

export interface UseVirtualQueueResult {
  status: StatusAtendimento;
  posicao: PosicaoFilaResponse | null;
  prioridadeEfetiva: number;
  chamadaAtiva: ChamadaAtivaState | null;
  recusarChamada: () => Promise<void>;
  cancelarFila: (motivo?: string) => Promise<void>;
  marcarNoShow: () => void;
  marcarCancelado: () => void;
  atualizarPrioridadeReclassificada: (novaPrioridade: number) => void;
  isRecusando: boolean;
}

/**
 * Hook headless da Sala de Espera Virtual (Deepening #4).
 * Consolida polling + WebSocket, encerra automaticamente em estados terminais
 * (`PACIENTE_AUSENTE`, `CANCELADO_PACIENTE`, `CONCLUIDO`), restaura TTL após F5
 * via `chamada_iniciada_em`/`ttl_segundos` e integra recusa com `POST /fila/cancelar`.
 * @see docs/user-stories/US-08-atendimento-chamada-no-show.md
 */
export function useVirtualQueue(params: { session: StoredPatientSession }): UseVirtualQueueResult {
  const { session } = params;
  const queryClient = useQueryClient();
  const atendimentoId = session.atendimentoId ?? "";
  const token = session.token;

  const [chamadaEvent, setChamadaEvent] = useState<IncomingCallEvent | null>(null);
  const [terminalStatusOverride, setTerminalStatusOverride] = useState<StatusAtendimento | null>(
    null,
  );
  const [prioridadeOverride, setPrioridadeOverride] = useState<number | null>(null);

  const { mutateAsync: executarCancelamento, isPending: isRecusando } = useCancelarFila();

  const { data: posicaoData } = usePosicaoFila({
    atendimentoId,
    token,
    pollingInterval: (query) => {
      const latestStatus = query.state.data?.status;
      if (
        terminalStatusOverride ||
        chamadaEvent ||
        (latestStatus && TERMINAL_QUEUE_STATUSES.has(latestStatus))
      ) {
        return false;
      }
      return settings.network.queuePollingIntervalMs;
    },
    enabled: Boolean(atendimentoId && !terminalStatusOverride),
  });

  const statusAtual = posicaoData?.status ?? session.status ?? "TRIADO_AGUARDANDO_ELEGIBILIDADE";
  const statusEfetivo = terminalStatusOverride ?? statusAtual;
  const isTerminal = TERMINAL_QUEUE_STATUSES.has(statusEfetivo);

  const handleCallReceived = useCallback((event: IncomingCallEvent) => {
    setChamadaEvent(event);
  }, []);

  const handleQueueEvent = useCallback(() => {
    if (atendimentoId && !isTerminal) {
      queryClient.invalidateQueries({
        queryKey: ["queue", "posicao", atendimentoId],
      });
    }
  }, [atendimentoId, isTerminal, queryClient]);

  useQueueSocket({
    atendimentoId,
    token,
    enabled: Boolean(atendimentoId && !isTerminal),
    onCallReceived: handleCallReceived,
    onEvent: handleQueueEvent,
  });

  const chamadaAtiva: ChamadaAtivaState | null =
    !isTerminal && (Boolean(chamadaEvent) || statusEfetivo === "CHAMANDO_PACIENTE")
      ? {
          sala: `room_${atendimentoId}`,
          chamadaIniciadaEm:
            chamadaEvent?.chamada_iniciada_em ?? posicaoData?.chamada_iniciada_em ?? "",
          ttlSegundos:
            chamadaEvent?.ttl_segundos ??
            posicaoData?.ttl_segundos ??
            settings.clinical.callRingTtlSeconds,
        }
      : null;

  const cancelarFila = useCallback(
    async (motivo = "Desistência voluntária pelo paciente") => {
      if (!atendimentoId) return;
      await executarCancelamento({
        atendimentoId,
        token,
        body: { motivo },
      });
      setChamadaEvent(null);
      setTerminalStatusOverride("CANCELADO_PACIENTE");
    },
    [atendimentoId, executarCancelamento, token],
  );

  const recusarChamada = useCallback(async () => {
    await cancelarFila("Chamada médica recusada pelo paciente");
  }, [cancelarFila]);

  const marcarNoShow = useCallback(() => {
    setChamadaEvent(null);
    setTerminalStatusOverride("PACIENTE_AUSENTE");
  }, []);

  const marcarCancelado = useCallback(() => {
    setChamadaEvent(null);
    setTerminalStatusOverride("CANCELADO_PACIENTE");
  }, []);

  const atualizarPrioridadeReclassificada = useCallback(
    (novaPrioridade: number) => {
      setPrioridadeOverride(novaPrioridade);
      if (atendimentoId) {
        queryClient.invalidateQueries({
          queryKey: ["queue", "posicao", atendimentoId],
        });
      }
    },
    [atendimentoId, queryClient],
  );

  return {
    status: statusEfetivo,
    posicao: posicaoData ?? null,
    prioridadeEfetiva:
      prioridadeOverride ?? posicaoData?.prioridade_clinica ?? session.prioridadeClinica ?? 3,
    chamadaAtiva,
    recusarChamada,
    cancelarFila,
    marcarNoShow,
    marcarCancelado,
    atualizarPrioridadeReclassificada,
    isRecusando,
  };
}
