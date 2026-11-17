import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import type { StoredPatientSession } from "@/lib/session-storage";

export const MOCK_CITIZEN_SESSION: StoredPatientSession = {
  token: "mock-citizen-jwt-token",
  pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
  role: "PACIENTE",
  tipo: "otp",
};

export const MOCK_CITIZEN_ACTIVE_SESSION: StoredPatientSession = {
  ...MOCK_CITIZEN_SESSION,
  atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
  prioridadeClinica: 4,
  status: "APTO_PARA_CHAMADA",
};

export function renderCitizenRoute(ui: ReactNode, initialPath = "/home") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const testRootRoute = createRootRoute({
    component: () => (
      <QueryClientProvider client={queryClient}>
        <Outlet />
      </QueryClientProvider>
    ),
  });

  const routes = [
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/",
      component: () => <div>Landing Page Mock</div>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/home",
      component: () => <>{initialPath === "/home" ? ui : <div>Home Mock</div>}</>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/agendar",
      component: () => <div>Agendar Mock</div>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/fila",
      component: () => <div>Fila Mock</div>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/historico",
      component: () => <>{initialPath === "/historico" ? ui : <div>Histórico Mock</div>}</>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/receitas",
      component: () => <>{initialPath === "/receitas" ? ui : <div>Receitas Mock</div>}</>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/perfil",
      component: () => <>{initialPath === "/perfil" ? ui : <div>Perfil Mock</div>}</>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/triagem",
      component: () => <div>Triagem Mock</div>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/validar",
      component: () => <>{initialPath === "/validar" ? ui : <div>Validar Mock</div>}</>,
    }),
    createRoute({
      getParentRoute: () => testRootRoute,
      path: "/validar/$token",
      component: () => <div>Validar Token Destino</div>,
    }),
  ];

  const routeTree = testRootRoute.addChildren(routes);
  const history = createMemoryHistory({ initialEntries: [initialPath] });
  const testRouter = createRouter({
    routeTree,
    history,
  });

  const rendered = render(<RouterProvider router={testRouter as never} />);
  return { ...rendered, history, queryClient };
}
