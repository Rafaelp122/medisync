import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyPostConsultationPage = lazyRouteComponent(
  () => import("@/features/consultation/pages/post-consultation-page"),
  "PostConsultationPage",
);

export const posConsultaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/pos-consulta",
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
    const { session } = posConsultaRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <CitizenShellLayout session={session}>
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyPostConsultationPage session={session} />
        </Suspense>
      </CitizenShellLayout>
    );
  },
});
