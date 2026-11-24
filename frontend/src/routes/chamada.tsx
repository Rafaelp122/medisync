import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import {
  getStoredCallData,
  getStoredSession,
  type StoredPatientSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyConsultationRoomPage = lazyRouteComponent(
  () => import("@/features/consultation/pages/consultation-room-page"),
  "ConsultationRoomPage",
);

export const chamadaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chamada",
  beforeLoad: ({ location }) => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }

    const callData = location.state?.callData ?? getStoredCallData();
    if (!callData?.token) {
      throw redirect({ to: session.atendimentoId ? "/fila" : "/home" });
    }

    return { session, callData };
  },
  component: function RouteComponent() {
    const context = chamadaRoute.useRouteContext() as {
      session: StoredPatientSession;
      callData: LiveKitTokenResponse;
    };
    return (
      <Suspense fallback={<RoutePendingFallback />}>
        <LazyConsultationRoomPage session={context.session} callData={context.callData} />
      </Suspense>
    );
  },
});
