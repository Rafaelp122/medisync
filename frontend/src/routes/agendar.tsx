import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { z } from "zod";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const agendarSearchSchema = z.object({
  especialidade: z.string().optional(),
});

const LazyScheduleAppointmentPage = lazyRouteComponent(
  () => import("@/features/scheduling/pages/schedule-appointment-page"),
  "ScheduleAppointmentPage",
);

export const agendarRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/agendar",
  validateSearch: (search: Record<string, unknown>) => agendarSearchSchema.parse(search),
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    return { session };
  },
  component: function AgendarRouteComponent() {
    const { session } = agendarRoute.useRouteContext() as { session: StoredPatientSession };
    const search = agendarRoute.useSearch();
    return (
      <CitizenShellLayout session={session}>
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyScheduleAppointmentPage initialEspecialidade={search.especialidade} />
        </Suspense>
      </CitizenShellLayout>
    );
  },
});
