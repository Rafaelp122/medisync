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
import { agendarRoute } from "@/routes/agendar";
import { cadastroRoute } from "@/routes/cadastro";
import { chamadaRoute } from "@/routes/chamada";
import { entrarRoute } from "@/routes/entrar";
import { filaRoute } from "@/routes/fila";
import { gestorRoute } from "@/routes/gestor";
import { historicoRoute } from "@/routes/historico";
import { homeRoute } from "@/routes/home";
import { indexRoute } from "@/routes/index";
import { internoLoginRoute } from "@/routes/interno-login";
import { medicoRoute } from "@/routes/medico";
import { otpRoute } from "@/routes/otp";
import { perfilRoute } from "@/routes/perfil";
import { posConsultaRoute } from "@/routes/pos-consulta";
import { receitasRoute } from "@/routes/receitas";
import { rootRoute } from "@/routes/root";
import { triagemRoute } from "@/routes/triagem";
import { validarRoute } from "@/routes/validar";
import { validarTokenRoute } from "@/routes/validar-token";

export const routeTree = rootRoute.addChildren([
  indexRoute,
  entrarRoute,
  cadastroRoute,
  internoLoginRoute,
  homeRoute,
  agendarRoute,
  historicoRoute,
  receitasRoute,
  perfilRoute,
  triagemRoute,
  otpRoute,
  filaRoute,
  chamadaRoute,
  posConsultaRoute,
  validarRoute,
  validarTokenRoute,
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
