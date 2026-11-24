import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyProfilePage = lazyRouteComponent(
  () => import("@/features/citizen/pages/profile-page"),
  "ProfilePage",
);

const LazyEnriquecimentoFase2Form = lazyRouteComponent(
  () => import("@/features/onboarding/components/enriquecimento-fase2-form"),
  "EnriquecimentoFase2Form",
);

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
      <Suspense fallback={<RoutePendingFallback />}>
        <LazyProfilePage
          session={session}
          renderEnrichmentForm={({ pacienteId, token, onConcluido }) => (
            <Suspense fallback={<RoutePendingFallback />}>
              <LazyEnriquecimentoFase2Form
                pacienteId={pacienteId}
                token={token}
                onConcluido={onConcluido}
              />
            </Suspense>
          )}
        />
      </Suspense>
    );
  },
});
