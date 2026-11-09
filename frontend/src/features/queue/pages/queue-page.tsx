import { useNavigate } from "@tanstack/react-router";
import type React from "react";
import { useState } from "react";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { VirtualWaitingRoom } from "@/features/queue/components/virtual-waiting-room";
import {
  clearStoredSession,
  type StoredPatientSession,
  saveStoredCallData,
} from "@/lib/session-storage";

export interface QueuePageProps {
  session: StoredPatientSession;
  renderComplementarForm?: (props: {
    pacienteId: string;
    token: string;
    onConcluido: () => void;
    onPular: () => void;
  }) => React.ReactNode;
}

export function QueuePage({ session, renderComplementarForm }: QueuePageProps) {
  const navigate = useNavigate();
  const [modalComplementarAberto, setModalComplementarAberto] = useState(false);

  const handleEncerrarSessao = () => {
    clearStoredSession();
    navigate({ to: "/" });
  };

  const handleAtendimentoIniciado = (data: LiveKitTokenResponse) => {
    setModalComplementarAberto(false);
    saveStoredCallData(data);
    navigate({
      to: "/chamada",
      state: { callData: data },
    });
  };

  return (
    <>
      <VirtualWaitingRoom
        session={session}
        onEncerrarSessao={handleEncerrarSessao}
        onAtendimentoIniciado={handleAtendimentoIniciado}
        onComplementarCadastro={() => setModalComplementarAberto(true)}
      />

      <Dialog open={modalComplementarAberto} onOpenChange={setModalComplementarAberto}>
        <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto p-0 border-0 bg-transparent shadow-none">
          <DialogHeader className="sr-only">
            <DialogTitle>Complementação Cadastral (Fase 2)</DialogTitle>
            <DialogDescription>
              Complemente seus dados de endereço e alergias para o prontuário médico. Sua vaga na
              fila virtual permanece garantida.
            </DialogDescription>
          </DialogHeader>
          {renderComplementarForm
            ? renderComplementarForm({
                pacienteId: session.pacienteId,
                token: session.token,
                onConcluido: () => setModalComplementarAberto(false),
                onPular: () => setModalComplementarAberto(false),
              })
            : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
