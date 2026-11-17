import { createRoute, redirect } from "@tanstack/react-router";
import { PostConsultationPage } from "@/features/consultation/pages/post-consultation-page";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

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
        <PostConsultationPage session={session} />
      </CitizenShellLayout>
    );
  },
});
