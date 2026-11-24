import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyHistoryPage = lazyRouteComponent(
  () => import("@/features/citizen/pages/history-page"),
  "HistoryPage",
);

export const historicoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/historico",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    return { session };
  },
  component: function HistoricoRouteComponent() {
    const { session } = historicoRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <Suspense fallback={<RoutePendingFallback />}>
        <LazyHistoryPage session={session} />
      </Suspense>
    );
  },
});
