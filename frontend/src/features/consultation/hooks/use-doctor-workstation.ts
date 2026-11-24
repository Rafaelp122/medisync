import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { AgendamentoResponse, ChamarProximoResponse } from "@/api/generated/types.gen";
import {
  PAINEL_TELEMETRIA_QUERY_KEY_PREFIX,
  usePainelTelemetria,
} from "@/api/hooks/use-painel-telemetria";
import { formatarEspecialidadeNome } from "@/lib/formatters";
import { useChamarProximo } from "../api/use-chamar-proximo";
import { useLiveKitToken } from "../api/use-livekit-token";
import type { AtendimentoClinicoSnapshot } from "../context/consultation-encounter-provider";

function buildSnapshotFromAlocacao(
  data: ChamarProximoResponse,
  medicoId: string,
  medicoNome: string,
  crmUf: string,
  token?: string,
): AtendimentoClinicoSnapshot {
  const pacienteId = data.paciente_id ?? data.atendimento_id ?? "";
  return {
    atendimentoId: data.atendimento_id ?? "",
    pacienteId,
    pacienteNome: `Paciente #${pacienteId.slice(0, 8)}`,
    pacienteIdentificador: "Protegido (LGPD)",
    medicoId,
    medicoNome,
    crmUf,
    prioridadeClinica: data.prioridade_clinica ?? 3,
    queixaPrincipal: "Acolhimento clínico em fila virtual.",
    chamadaIniciadaEm: data.chamada_iniciada_em,
    ttlSegundos: data.ttl_segundos,
    token,
  };
}

/**
 * Hook headless de controle da Estação Clínica (fila, agenda programada, LiveKit e auto-logout).
 */
export function useDoctorWorkstation(params: {
  medicoId: string;
  medicoNome: string;
  crmUf: string;
  token?: string;
  onLogout?: () => void;
  idleTimeoutMs: number;
}) {
  const { medicoId, medicoNome, crmUf, token, onLogout, idleTimeoutMs } = params;
  const [atendimentoAtivo, setAtendimentoAtivo] = useState<AtendimentoClinicoSnapshot | null>(null);
  const [mensagemFilaVazia, setMensagemFilaVazia] = useState<string | null>(null);
  const livekitAtendimentoIdRef = useRef<string | null>(null);
  const onLogoutRef = useRef(onLogout);
  onLogoutRef.current = onLogout;
  const hasOnLogout = Boolean(onLogout);

  useEffect(() => {
    if (!hasOnLogout) return;
    let timer: ReturnType<typeof setTimeout>;
    const resetTimer = () => {
      clearTimeout(timer);
      timer = setTimeout(() => onLogoutRef.current?.(), idleTimeoutMs);
    };
    const activityEvents = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;
    for (const event of activityEvents) {
      window.addEventListener(event, resetTimer, { passive: true });
    }
    resetTimer();
    return () => {
      clearTimeout(timer);
      for (const event of activityEvents) {
        window.removeEventListener(event, resetTimer);
      }
    };
  }, [hasOnLogout, idleTimeoutMs]);

  const queryClient = useQueryClient();
  const { data: painelTelemetria, isLoading: isCarregandoPainel } = usePainelTelemetria({
    refetchInterval: 10_000,
  });
  const totalPacientesFila = painelTelemetria?.total_pacientes_fila ?? 0;

  const { mutate: chamarProximo, isPending: isCallingNext } = useChamarProximo();
  const {
    data: rawLivekitData,
    variables: livekitVariables,
    mutate: emitirLivekitToken,
    reset: resetLivekitToken,
  } = useLiveKitToken(atendimentoAtivo?.atendimentoId || "");

  const limparAtendimento = useCallback(() => {
    livekitAtendimentoIdRef.current = null;
    resetLivekitToken();
    setAtendimentoAtivo(null);
  }, [resetLivekitToken]);

  const iniciarSalaParaAtendimento = (snapshot: AtendimentoClinicoSnapshot) => {
    livekitAtendimentoIdRef.current = snapshot.atendimentoId;
    resetLivekitToken();
    setAtendimentoAtivo(snapshot);
    emitirLivekitToken(
      {
        token,
        atendimento_id: snapshot.atendimentoId,
        participant_id: medicoId,
        role: "medico",
        participant_name: medicoNome,
        is_publisher: true,
        ttl_seconds: 3600,
      },
      {
        onSuccess: (_data, variables) => {
          if (variables.atendimento_id !== livekitAtendimentoIdRef.current) {
            resetLivekitToken();
          }
        },
      },
    );
  };

  const livekitData =
    atendimentoAtivo?.atendimentoId &&
    rawLivekitData &&
    livekitVariables?.atendimento_id === atendimentoAtivo.atendimentoId &&
    livekitAtendimentoIdRef.current === atendimentoAtivo.atendimentoId
      ? rawLivekitData
      : undefined;

  const handleChamarProximo = () => {
    setMensagemFilaVazia(null);
    chamarProximo(
      { token },
      {
        onSuccess: (data) => {
          if (data.alocado && data.atendimento_id) {
            iniciarSalaParaAtendimento(
              buildSnapshotFromAlocacao(data, medicoId, medicoNome, crmUf, token),
            );
          } else {
            setMensagemFilaVazia(
              data.mensagem ||
                "Nenhum paciente aguardando na fila virtual no momento. Aguarde novos ingressos.",
            );
          }
        },
        onError: (err) => {
          setMensagemFilaVazia(
            err.detail ||
              "Erro ao alocar paciente da fila virtual. Verifique a autenticação e conexão com o servidor.",
          );
        },
        onSettled: () => {
          void queryClient.invalidateQueries({ queryKey: [...PAINEL_TELEMETRIA_QUERY_KEY_PREFIX] });
        },
      },
    );
  };

  const handleAgendamentoIniciado = (agendamento: AgendamentoResponse) => {
    if (!agendamento.atendimento_id) return;
    setMensagemFilaVazia(null);
    iniciarSalaParaAtendimento({
      atendimentoId: agendamento.atendimento_id,
      pacienteId: agendamento.paciente_id,
      pacienteNome: `Paciente #${agendamento.paciente_id.slice(0, 8)}`,
      pacienteIdentificador: "Protegido (LGPD)",
      medicoId,
      medicoNome,
      crmUf,
      prioridadeClinica: 3,
      queixaPrincipal:
        agendamento.observacoes?.trim() ||
        `Teleconsulta agendada · ${formatarEspecialidadeNome(agendamento.especialidade)}`,
      chamadaIniciadaEm: agendamento.atualizado_em,
      ttlSegundos: 900,
      token,
    });
  };

  return {
    atendimentoAtivo,
    mensagemFilaVazia,
    totalPacientesFila,
    isCarregandoPainel,
    isCallingNext,
    livekitData,
    limparAtendimento,
    handleChamarProximo,
    handleAgendamentoIniciado,
  };
}
