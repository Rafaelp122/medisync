import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
  type StoredPatientSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyTriagemPage = lazyRouteComponent(
  () => import("@/features/onboarding/pages/triagem-page"),
  "TriagemPage",
);

export const triagemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/triagem",
  beforeLoad: () => {
    const doctor = getStoredDoctorSession();
    if (doctor && (!doctor.papel || doctor.papel === "MEDICO")) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager?.papel === "GESTOR_UNIDADE") {
      throw redirect({ to: "/gestor" });
    }

    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }

    if (session.atendimentoId) {
      throw redirect({ to: "/fila" });
    }

    return { session };
  },
  component: function TriagemRouteComponent() {
    const { session } = triagemRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <CitizenShellLayout session={session}>
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyTriagemPage session={session} />
        </Suspense>
      </CitizenShellLayout>
    );
  },
});
