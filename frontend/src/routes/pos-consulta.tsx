import { createRoute, redirect } from "@tanstack/react-router";
import { PostConsultationPage } from "@/features/consultation/pages/post-consultation-page";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
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
  component: function RouteComponent() {
    const { session } = posConsultaRoute.useRouteContext() as { session: StoredPatientSession };
    return <PostConsultationPage session={session} />;
  },
});
