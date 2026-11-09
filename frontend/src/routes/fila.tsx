import { createRoute, redirect } from "@tanstack/react-router";
import { EnriquecimentoFase2Form } from "@/features/onboarding/components/enriquecimento-fase2-form";
import { QueuePage } from "@/features/queue/pages/queue-page";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
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
  component: function RouteComponent() {
    const { session } = filaRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <QueuePage
        session={session}
        renderComplementarForm={({ pacienteId, token, onConcluido, onPular }) => (
          <EnriquecimentoFase2Form
            pacienteId={pacienteId}
            token={token}
            onConcluido={onConcluido}
            onPular={onPular}
          />
        )}
      />
    );
  },
});
