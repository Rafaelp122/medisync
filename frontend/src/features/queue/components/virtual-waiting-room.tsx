import { useCallback, useState } from "react";
import type {
  LiveKitTokenResponse,
  WebAuthnRegisterVerifyResponse,
} from "@/api/generated/types.gen";
import { SamuEmergencyModal } from "@/components/samu-emergency-modal";
import type { StoredPatientSession } from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import type { RegisterPasskeyCredentialParams } from "@/lib/webauthn";
import { useVirtualQueue } from "../hooks/use-virtual-queue";
import { CancelarFilaDialog } from "./cancelar-fila-dialog";
import { IncomingCallRingModal } from "./incoming-call-ring-modal";
import { PasskeyInvitationCard } from "./passkey-invitation-card";
import { PioraClinicaModal } from "./piora-clinica-modal";
import { QueuePositionCard } from "./queue-position-card";
import { QueueTerminalStateCard } from "./queue-terminal-state-card";
import { QueueWaitingActionsCard } from "./queue-waiting-actions-card";
import { RegularizarElegibilidadeCard } from "./regularizar-elegibilidade-card";

export interface VirtualWaitingRoomProps {
  session: StoredPatientSession;
  onEncerrarSessao?: () => void;
  onAtendimentoIniciado?: (data: LiveKitTokenResponse) => void;
  onComplementarCadastro?: () => void;
  onRegisterPasskey?: (
    params: RegisterPasskeyCredentialParams,
  ) => Promise<WebAuthnRegisterVerifyResponse>;
  className?: string;
}

/**
 * Sala de Espera Virtual do Paciente (<150L via Deepening `useVirtualQueue`).
 * @see docs/user-stories/US-08-atendimento-chamada-no-show.md
 * @see docs/how-to/patient-virtual-waiting-room.md
 */
export function VirtualWaitingRoom({
  session,
  onEncerrarSessao,
  onAtendimentoIniciado,
  onComplementarCadastro,
  onRegisterPasskey,
  className,
}: VirtualWaitingRoomProps) {
  const atendimentoId = session.atendimentoId ?? "";
  const token = session.token;

  const [modalPioraAberto, setModalPioraAberto] = useState(false);
  const [modalCancelarAberto, setModalCancelarAberto] = useState(false);
  const [modalSamuAberto, setModalSamuAberto] = useState(false);
  const [samuOrientacoes, setSamuOrientacoes] = useState<string | null>(null);

  const queue = useVirtualQueue({ session });

  const handleEmergenciaSamu = useCallback((orientacoes?: string | null) => {
    setSamuOrientacoes(orientacoes ?? null);
    setModalSamuAberto(true);
  }, []);

  if (
    queue.status === "PACIENTE_AUSENTE" ||
    queue.status === "CANCELADO_PACIENTE" ||
    queue.status === "CANCELADO" ||
    queue.status === "CONCLUIDO"
  ) {
    return (
      <QueueTerminalStateCard
        status={queue.status}
        className={className}
        onEncerrarSessao={onEncerrarSessao}
      />
    );
  }

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

      <QueuePositionCard
        atendimentoId={atendimentoId}
        posicao={queue.posicao?.posicao}
        totalAguardando={queue.posicao?.total_aguardando}
        tempoEstimadoSegundos={queue.posicao?.tempo_estimado_segundos}
        prioridadeClinica={queue.prioridadeEfetiva}
        status={queue.status}
      />

      {queue.status === "TRIADO_AGUARDANDO_ELEGIBILIDADE" && atendimentoId && (
        <RegularizarElegibilidadeCard atendimentoId={atendimentoId} token={token} />
      )}

      <PasskeyInvitationCard token={token} onRegisterPasskey={onRegisterPasskey} />

      <QueueWaitingActionsCard
        onAbrirPiora={() => setModalPioraAberto(true)}
        onComplementarCadastro={onComplementarCadastro}
        onAbrirCancelar={() => setModalCancelarAberto(true)}
      />

      <PioraClinicaModal
        open={modalPioraAberto}
        onOpenChange={setModalPioraAberto}
        atendimentoId={atendimentoId}
        token={token}
        onEmergenciaSamu={handleEmergenciaSamu}
        onReclassificado={(data) => queue.atualizarPrioridadeReclassificada(data.novaPrioridade)}
      />

      <CancelarFilaDialog
        open={modalCancelarAberto}
        onOpenChange={setModalCancelarAberto}
        atendimentoId={atendimentoId}
        token={token}
        onCancelado={queue.marcarCancelado}
      />

      <SamuEmergencyModal
        open={modalSamuAberto}
        onOpenChange={setModalSamuAberto}
        orientacoes={samuOrientacoes}
        onConfirmarSaida={onEncerrarSessao}
      />

      <IncomingCallRingModal
        open={Boolean(queue.chamadaAtiva)}
        atendimentoId={atendimentoId}
        pacienteId={session.pacienteId}
        token={token}
        ttlSegundos={queue.chamadaAtiva?.ttlSegundos}
        chamadaIniciadaEm={queue.chamadaAtiva?.chamadaIniciadaEm}
        onAtendido={(data) => onAtendimentoIniciado?.(data)}
        onNoShow={queue.marcarNoShow}
        onRecusar={queue.recusarChamada}
        isRecusando={queue.isRecusando}
      />
    </div>
  );
}
