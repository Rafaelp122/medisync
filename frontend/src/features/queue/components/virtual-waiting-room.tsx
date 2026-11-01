import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { SamuEmergencyModal } from "@/components/samu-emergency-modal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { StoredPatientSession } from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { usePosicaoFila } from "../api/use-posicao-fila";
import { type IncomingCallEvent, useQueueSocket } from "../api/use-queue-socket";
import { CancelarFilaDialog } from "./cancelar-fila-dialog";
import { IncomingCallRingModal } from "./incoming-call-ring-modal";
import { PasskeyInvitationCard } from "./passkey-invitation-card";
import { PioraClinicaModal } from "./piora-clinica-modal";
import { QueuePositionCard } from "./queue-position-card";

export interface VirtualWaitingRoomProps {
  session: StoredPatientSession;
  onEncerrarSessao?: () => void;
  onAtendimentoIniciado?: (data: LiveKitTokenResponse) => void;
  onComplementarCadastro?: () => void;
  className?: string;
}

/**
 * Sala de Espera Virtual do Paciente (RF-03, RN01, RN02).
 *
 * Gerencia a posição em tempo real na fila via polling e streaming WebSocket,
 * despacha a convocação médica de 45s (IncomingCallRingModal), reavaliação de risco
 * (PioraClinicaModal / RF-06) e salvaguarda SAMU 192 (RN04).
 *
 * @see docs/user-stories/US-07-alocacao-chamada-medica.md
 * @see docs/user-stories/US-08-atendimento-chamada-no-show.md
 * @see docs/how-to/patient-virtual-waiting-room.md
 */
export function VirtualWaitingRoom({
  session,
  onEncerrarSessao,
  onAtendimentoIniciado,
  onComplementarCadastro,
  className,
}: VirtualWaitingRoomProps) {
  const queryClient = useQueryClient();
  const atendimentoId = session.atendimentoId ?? "";
  const token = session.token;

  // Modais e Estados Visuais
  const [modalPioraAberto, setModalPioraAberto] = useState(false);
  const [modalCancelarAberto, setModalCancelarAberto] = useState(false);
  const [modalSamuAberto, setModalSamuAberto] = useState(false);
  const [samuOrientacoes, setSamuOrientacoes] = useState<string | null>(null);

  // Estado de Chamada Médica Ativa (45s Ring)
  const [chamadaAtiva, setChamadaAtiva] = useState<IncomingCallEvent | null>(null);
  const [isPacienteAusente, setIsPacienteAusente] = useState(false);
  const [isCancelado, setIsCancelado] = useState(false);

  // Prioridade e Posição Reclassificadas Localmente (após Piora)
  const [prioridadeOverride, setPrioridadeOverride] = useState<number | null>(null);

  // Polling resiliente da fila
  const { data: posicaoData } = usePosicaoFila({
    atendimentoId,
    token,
    pollingInterval: chamadaAtiva ? false : 5000,
    enabled: Boolean(atendimentoId && !isPacienteAusente && !isCancelado),
  });

  // WebSocket de Fila em Tempo Real
  const handleCallReceived = useCallback((event: IncomingCallEvent) => {
    setChamadaAtiva(event);
  }, []);

  const handleQueueEvent = useCallback(() => {
    // Invalidação imediata do cache para avanço de fila em tempo real (DoD 1)
    if (atendimentoId) {
      queryClient.invalidateQueries({
        queryKey: ["queue", "posicao", atendimentoId],
      });
    }
  }, [atendimentoId, queryClient]);

  useQueueSocket({
    atendimentoId,
    token,
    enabled: Boolean(atendimentoId && !isPacienteAusente && !isCancelado),
    onCallReceived: handleCallReceived,
    onEvent: handleQueueEvent,
  });

  // Se o polling detectar status de chamada médica antes do WS
  const statusAtual = posicaoData?.status ?? session.status ?? "TRIADO_AGUARDANDO_ELEGIBILIDADE";
  const statusEfetivo = isPacienteAusente
    ? "PACIENTE_AUSENTE"
    : isCancelado
      ? "CANCELADO"
      : statusAtual;

  const prioridadeEfetiva = prioridadeOverride ?? session.prioridadeClinica ?? 3;

  // Handlers de Ações
  const handleAtendido = useCallback(
    (data: LiveKitTokenResponse) => {
      setChamadaAtiva(null);
      onAtendimentoIniciado?.(data);
    },
    [onAtendimentoIniciado],
  );

  const handleNoShow = useCallback(() => {
    setChamadaAtiva(null);
    setIsPacienteAusente(true);
  }, []);

  const handleEmergenciaSamu = useCallback((orientacoes?: string | null) => {
    setSamuOrientacoes(orientacoes ?? null);
    setModalSamuAberto(true);
  }, []);

  const handleReclassificado = useCallback(
    (data: { novaPrioridade: number; novaPosicao?: number | null }) => {
      setPrioridadeOverride(data.novaPrioridade);
      if (atendimentoId) {
        queryClient.invalidateQueries({
          queryKey: ["queue", "posicao", atendimentoId],
        });
      }
    },
    [atendimentoId, queryClient],
  );

  // 1. Tela de Emergência Máxima SAMU (Escape RN04)
  if (modalSamuAberto) {
    return (
      <SamuEmergencyModal
        open={true}
        orientacoes={samuOrientacoes}
        onConfirmarSaida={onEncerrarSessao}
      />
    );
  }

  // 2. Tela de No-Show / Paciente Ausente
  if (statusEfetivo === "PACIENTE_AUSENTE") {
    return (
      <Card
        className={cn(
          "w-full max-w-lg mx-auto shadow-lg text-center space-y-4 border-destructive/30",
          className,
        )}
      >
        <CardHeader>
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive mb-2">
            <span className="text-3xl" aria-hidden="true">
              ⏱️
            </span>
          </div>
          <CardTitle className="text-2xl font-bold text-destructive">
            Chamada Não Atendida
          </CardTitle>
          <CardDescription className="text-sm text-pretty">
            O médico plantonista chamou seu atendimento, mas não houve confirmação dentro da janela
            de 45 segundos (RN02).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-left">
          <p className="text-xs text-muted-foreground leading-relaxed">
            Para garantir agilidade no pronto atendimento e evitar atrasos na fila, sua vaga foi
            liberada para o próximo paciente. Se você ainda precisa de assistência médica, inicie um
            novo acolhimento.
          </p>
          {onEncerrarSessao && (
            <Button type="button" variant="default" className="w-full" onClick={onEncerrarSessao}>
              Iniciar Novo Atendimento
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  // 3. Tela de Cancelamento Voluntário
  if (statusEfetivo === "CANCELADO") {
    return (
      <Card className={cn("w-full max-w-lg mx-auto shadow-lg text-center space-y-4", className)}>
        <CardHeader>
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-muted text-muted-foreground mb-2">
            <span className="text-3xl" aria-hidden="true">
              ✕
            </span>
          </div>
          <CardTitle className="text-xl font-bold text-foreground">Atendimento Cancelado</CardTitle>
          <CardDescription className="text-sm">
            Sua permanência na fila virtual foi encerrada com sucesso (RN06).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {onEncerrarSessao && (
            <Button type="button" variant="outline" className="w-full" onClick={onEncerrarSessao}>
              Voltar ao Início
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  // 4. Sala de Espera Virtual Ativa
  return (
    <div className={cn("w-full max-w-xl mx-auto space-y-4", className)}>
      <header className="text-center space-y-1">
        <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
          Sala de Espera Virtual
        </h2>
        <p className="text-xs sm:text-sm text-muted-foreground">
          Mantenha esta tela aberta. Você será notificado por áudio e vídeo assim que o médico
          convocar.
        </p>
      </header>

      {/* Card Principal de Posição na Fila */}
      <QueuePositionCard
        atendimentoId={atendimentoId}
        posicao={posicaoData?.posicao}
        totalAguardando={posicaoData?.total_aguardando}
        tempoEstimadoSegundos={posicaoData?.tempo_estimado_segundos}
        prioridadeClinica={prioridadeEfetiva}
        status={statusEfetivo}
      />

      {/* Convite Biométrico Passkeys (US-14) */}
      <PasskeyInvitationCard />

      {/* Salvaguarda de Deterioração Clínica & Ações do Paciente */}
      <Card className="border-border/80 shadow-sm">
        <CardContent className="pt-4 space-y-3">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-destructive/5 rounded-lg border border-destructive/15">
            <div className="text-left space-y-0.5">
              <span className="text-xs font-bold text-destructive block">
                Sentiu piora nos sintomas?
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Acione a reavaliação imediata de risco pelo protocolo de triagem (RF-06).
              </span>
            </div>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="w-full sm:w-auto shrink-0 font-semibold"
              onClick={() => setModalPioraAberto(true)}
            >
              Relatar Piora
            </Button>
          </div>

          {onComplementarCadastro && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-muted/40 rounded-lg border border-border">
              <div className="text-left space-y-0.5">
                <span className="text-xs font-semibold text-foreground block">
                  Prontuário e Dados Cadastrais
                </span>
                <span className="text-[11px] text-muted-foreground block">
                  Complete seu endereço e alergias para agilizar o atendimento médico.
                </span>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full sm:w-auto shrink-0 font-medium"
                onClick={onComplementarCadastro}
              >
                Completar Cadastro
              </Button>
            </div>
          )}

          <div className="flex justify-between items-center pt-1 border-t text-xs">
            <button
              type="button"
              onClick={() => setModalCancelarAberto(true)}
              className="text-muted-foreground hover:text-destructive underline-offset-4 hover:underline transition-colors py-1"
            >
              Desistir do atendimento
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Modal de Piora Clínica */}
      <PioraClinicaModal
        open={modalPioraAberto}
        onOpenChange={setModalPioraAberto}
        atendimentoId={atendimentoId}
        token={token}
        onEmergenciaSamu={handleEmergenciaSamu}
        onReclassificado={handleReclassificado}
      />

      {/* Modal de Cancelamento */}
      <CancelarFilaDialog
        open={modalCancelarAberto}
        onOpenChange={setModalCancelarAberto}
        atendimentoId={atendimentoId}
        token={token}
        onCancelado={() => setIsCancelado(true)}
      />

      {/* Modal Fullscreen de Chamada Médica (45s Ring) */}
      <IncomingCallRingModal
        open={Boolean(chamadaAtiva) || statusAtual === "CHAMANDO_PACIENTE"}
        atendimentoId={atendimentoId}
        pacienteId={session.pacienteId}
        token={token}
        ttlSegundos={chamadaAtiva?.ttl_segundos ?? 45}
        chamadaIniciadaEm={chamadaAtiva?.chamada_iniciada_em}
        onAtendido={handleAtendido}
        onNoShow={handleNoShow}
      />
    </div>
  );
}
