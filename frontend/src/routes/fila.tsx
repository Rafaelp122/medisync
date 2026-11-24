import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyQueuePage = lazyRouteComponent(
  () => import("@/features/queue/pages/queue-page"),
  "QueuePage",
);

const LazyEnriquecimentoFase2Form = lazyRouteComponent(
  () => import("@/features/onboarding/components/enriquecimento-fase2-form"),
  "EnriquecimentoFase2Form",
);

export const filaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/fila",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    if (!session.atendimentoId) {
      throw redirect({ to: "/home" });
    }
    return { session };
  },
  component: function RouteComponent() {
    const { session } = filaRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <CitizenShellLayout session={session}>
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyQueuePage
            session={session}
            renderComplementarForm={({ pacienteId, token, onConcluido, onPular }) => (
              <Suspense fallback={<RoutePendingFallback />}>
                <LazyEnriquecimentoFase2Form
                  pacienteId={pacienteId}
                  token={token}
                  onConcluido={onConcluido}
                  onPular={onPular}
                />
              </Suspense>
            )}
          />
        </Suspense>
      </CitizenShellLayout>
    );
  },
});
