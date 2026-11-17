import { createRoute, redirect } from "@tanstack/react-router";
import { ProfilePage } from "@/features/citizen/pages/profile-page";
import { EnriquecimentoFase2Form } from "@/features/onboarding/components/enriquecimento-fase2-form";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const perfilRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/perfil",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    return { session };
  },
  component: function PerfilRouteComponent() {
    const { session } = perfilRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <ProfilePage
        session={session}
        renderEnrichmentForm={({ pacienteId, token, onConcluido }) => (
          <EnriquecimentoFase2Form
            pacienteId={pacienteId}
            token={token}
            onConcluido={onConcluido}
          />
        )}
      />
    );
  },
});
