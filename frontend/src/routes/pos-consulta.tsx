import { createRoute, redirect, useNavigate } from "@tanstack/react-router";
import { PosConsultaSummary } from "@/features/consultation/components/pos-consulta-summary";
import {
  clearStoredCallData,
  clearStoredSession,
  getStoredSession,
  type StoredPatientSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const posConsultaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/pos-consulta",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token || !session.atendimentoId) {
      throw redirect({ to: "/" });
    }
    return { session };
  },
  component: PosConsultaPage,
});

function PosConsultaPage() {
  const navigate = useNavigate();
  const { session } = posConsultaRoute.useRouteContext() as { session: StoredPatientSession };

  const handleNovaConsulta = () => {
    clearStoredSession();
    clearStoredCallData();
    navigate({ to: "/" });
  };

  return (
    <PosConsultaSummary
      atendimentoId={session.atendimentoId ?? ""}
      token={session.token}
      onNovaConsulta={handleNovaConsulta}
    />
  );
}
