import { createRoute, redirect } from "@tanstack/react-router";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { ConsultationRoomPage } from "@/features/consultation/pages/consultation-room-page";
import {
  getStoredCallData,
  getStoredSession,
  type StoredPatientSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

interface ChamadaLocationState {
  callData?: LiveKitTokenResponse;
}

export const chamadaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chamada",
  beforeLoad: ({ location }) => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/" });
    }

    const state = location.state as ChamadaLocationState | undefined;
    const callData = state?.callData ?? getStoredCallData();
    if (!callData?.token) {
      throw redirect({ to: session.atendimentoId ? "/fila" : "/" });
    }

    return { session, callData };
  },
  component: function RouteComponent() {
    const context = chamadaRoute.useRouteContext() as {
      session: StoredPatientSession;
      callData: LiveKitTokenResponse;
    };
    return <ConsultationRoomPage session={context.session} callData={context.callData} />;
  },
});
