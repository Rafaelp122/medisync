import { createRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EnriquecimentoFase2Form } from "@/features/onboarding/components/enriquecimento-fase2-form";
import { VirtualWaitingRoom } from "@/features/queue/components/virtual-waiting-room";
import {
  clearStoredSession,
  getStoredSession,
  type StoredPatientSession,
  saveStoredCallData,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const filaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/fila",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token || !session.atendimentoId) {
      throw redirect({ to: "/" });
    }
    return { session };
  },
  component: FilaPage,
});

function FilaPage() {
  const navigate = useNavigate();
  const { session } = filaRoute.useRouteContext() as { session: StoredPatientSession };
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
          <EnriquecimentoFase2Form
            pacienteId={session.pacienteId}
            token={session.token}
            onConcluido={() => setModalComplementarAberto(false)}
            onPular={() => setModalComplementarAberto(false)}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
