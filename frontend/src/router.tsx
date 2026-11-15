import type { QueryClient } from "@tanstack/react-query";
import {
  createBrowserHistory,
  createRouter,
  Navigate,
  type RouterHistory,
} from "@tanstack/react-router";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { defaultQueryClient } from "@/lib/query-client";
import { isReducedMotionPreferred } from "@/lib/view-transitions";
import { chamadaRoute } from "@/routes/chamada";
import { filaRoute } from "@/routes/fila";
import { gestorRoute } from "@/routes/gestor";
import { indexRoute } from "@/routes/index";
import { loginRoute } from "@/routes/login";
import { medicoRoute } from "@/routes/medico";
import { otpRoute } from "@/routes/otp";
import { posConsultaRoute } from "@/routes/pos-consulta";
import { rootRoute } from "@/routes/root";
import { triagemRoute } from "@/routes/triagem";

export const routeTree = rootRoute.addChildren([
  indexRoute,
  triagemRoute,
  otpRoute,
  loginRoute,
  filaRoute,
  chamadaRoute,
  posConsultaRoute,
  medicoRoute,
  gestorRoute,
]);

export function createAppRouter(
  history?: RouterHistory,
  queryClient: QueryClient = defaultQueryClient,
) {
  return createRouter({
    routeTree,
    history: history ?? createBrowserHistory(),
    context: { queryClient },
    defaultPreload: "intent",
    defaultNotFoundComponent: () => <Navigate to="/" replace />,
    defaultViewTransition: !isReducedMotionPreferred(),
  });
}

export const router = createAppRouter();

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
  interface HistoryState {
    callData?: LiveKitTokenResponse;
  }
}
