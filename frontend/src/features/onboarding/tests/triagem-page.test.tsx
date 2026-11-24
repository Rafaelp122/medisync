import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleAdmitirPacienteApiV1FilaAdmissaoPost,
  handleEnrichmentFase2ApiV1OnboardingFase2Post,
} from "@/api/generated/msw.gen";
import { getStoredSession, saveStoredSession } from "@/lib/session-storage";
import { server } from "@/mocks/server";
import { TriagemPage } from "../pages/triagem-page";
import {
  createAdmissaoResponse,
  createEnrichmentFase2Response,
  MOCK_ATENDIMENTO_ID,
  MOCK_PACIENTE_ID,
} from "./fixtures";

const VALID_CITIZEN_JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMThmM2E1Yi03YjJjLTRiMmMtOGIyYy0wMThmM2E1YjdiMmMiLCJyb2xlIjoiUEFDSUVOVEUifQ.sig-preserve-jwt";

function renderTriagemPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const root = createRootRoute({
    component: () => <Outlet />,
  });

  const triagem = createRoute({
    getParentRoute: () => root,
    path: "/triagem",
    component: () => <TriagemPage />,
  });

  const home = createRoute({
    getParentRoute: () => root,
    path: "/home",
    component: () => <div>Portal Home</div>,
  });

  const fila = createRoute({
    getParentRoute: () => root,
    path: "/fila",
    component: () => <div>Sala de Espera Virtual</div>,
  });

  const router = createRouter({
    routeTree: root.addChildren([triagem, home, fila]),
    history: createMemoryHistory({ initialEntries: ["/triagem"] }),
  });

  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  return { ...view, router };
}

describe("TriagemPage (Preservação de JWT 3-partes em /triagem)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("IT-TRI-01: Cidadão autenticado com JWT 3-partes pula /onboarding/fase-1 e preserva JWT em medisync_session", async () => {
    saveStoredSession({
      token: VALID_CITIZEN_JWT,
      pacienteId: MOCK_PACIENTE_ID,
      role: "PACIENTE",
      tipo: "otp",
    });

    const fase1Spy = vi.fn();
    const capture: { body: Record<string, unknown> | null; authHeader: string | null } = {
      body: null,
      authHeader: null,
    };

    server.use(
      http.post("*/api/v1/onboarding/fase-1", () => {
        fase1Spy();
        return HttpResponse.json({ token: "two.parts" }, { status: 201 });
      }),
      handleAdmitirPacienteApiV1FilaAdmissaoPost(async ({ request }) => {
        capture.authHeader = request.headers.get("authorization");
        capture.body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          createAdmissaoResponse({
            atendimento_id: MOCK_ATENDIMENTO_ID,
            paciente_id: MOCK_PACIENTE_ID,
            prioridade_clinica: 3,
          }),
          { status: 201 },
        );
      }),
      handleEnrichmentFase2ApiV1OnboardingFase2Post(() =>
        HttpResponse.json(createEnrichmentFase2Response(), { status: 200 }),
      ),
    );

    const user = userEvent.setup();
    renderTriagemPage();

    // Passo de identificação civil não deve aparecer
    expect(await screen.findByLabelText(/o que você está sentindo\?/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/nome completo/i)).not.toBeInTheDocument();

    await user.type(
      screen.getByLabelText(/o que você está sentindo\?/i),
      "Dor abdominal moderada há 1 dia",
    );
    await user.click(screen.getByLabelText(/termo de consentimento livre e esclarecido/i));
    await user.click(screen.getByRole("button", { name: /entrar na fila virtual/i }));

    await waitFor(() => {
      expect(capture.body).not.toBeNull();
    });

    expect(fase1Spy).not.toHaveBeenCalled();
    expect(capture.authHeader).toBe(`Bearer ${VALID_CITIZEN_JWT}`);
    expect(capture.body?.paciente_id).toBe(MOCK_PACIENTE_ID);
    expect(String(capture.body?.tcle_hash)).toMatch(/^[0-9a-f]{64}$/);
    expect(capture.body?.tcle_hash).not.toBe("0".repeat(64));

    // Avançou para Enriquecimento (Fase 2) mantendo o JWT 3-partes original intacto
    expect(
      await screen.findByRole("heading", { name: /completar prontuário regulatório/i }),
    ).toBeInTheDocument();

    const sessaoAposAdmissao = getStoredSession();
    expect(sessaoAposAdmissao?.token).toBe(VALID_CITIZEN_JWT);
    expect(sessaoAposAdmissao?.token.split(".")).toHaveLength(3);
    expect(sessaoAposAdmissao?.tipo).toBe("otp");
    expect(sessaoAposAdmissao?.atendimentoId).toBe(MOCK_ATENDIMENTO_ID);

    // Pular Fase 2 para ir à fila mantendo JWT intacto
    await user.click(screen.getByRole("button", { name: /completar mais tarde/i }));
    expect(await screen.findByText(/sala de espera virtual/i)).toBeInTheDocument();
    expect(getStoredSession()?.token).toBe(VALID_CITIZEN_JWT);
  });
});
