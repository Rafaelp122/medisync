import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { handleValidarDocumentoApiV1DocumentsValidateTokenValidacaoGet } from "@/api/generated/msw.gen";
import { DocumentValidationPage } from "@/features/consultation/pages/document-validation-page";
import { server } from "@/mocks/server";

function renderValidationRoute(ui: ReactNode, initialPath = "/validar") {
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

  const indexRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/",
    component: () => <div>Landing Page Mock</div>,
  });

  const validarRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/validar",
    component: () => <>{ui}</>,
  });

  const history = createMemoryHistory({ initialEntries: [initialPath] });
  const testRouter = createRouter({
    routeTree: testRootRoute.addChildren([indexRoute, validarRoute]),
    history,
  });

  return render(<RouterProvider router={testRouter as never} />);
}

describe("DocumentValidationPage (/validar e /validar/$token)", () => {
  it("valida automaticamente quando token inicial é informado e exibe selo ICP-Brasil e dados LGPD mascarados", async () => {
    server.use(
      handleValidarDocumentoApiV1DocumentsValidateTokenValidacaoGet({
        body: {
          documento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b70",
          tipo_documento: "RECEITA_SIMPLES",
          status_documento: "ASSINADO",
          sha256_hash: "a3f4b5c6d7e8",
          assinado_em: "2026-11-15T15:30:00Z",
          emissor_medico_nome: "Dr. Eduardo Rocha",
          emissor_medico_crm: "123456",
          emissor_medico_uf: "SP",
          organizacao_nome: "UBS Centro · São Paulo",
          paciente_nome_mascarado: "M*** S***",
          paciente_cpf_mascarado: "***.456.789-**",
          assinatura_digital_valida: true,
          conformidade_icp_brasil: true,
          itens: [
            {
              medicamento: "Amoxicilina",
              dosagem: "500mg",
              posologia: "1 cápsula a cada 8 horas",
              duracao: "7 dias",
              controle_especial: false,
            },
          ],
        },
      }),
    );

    renderValidationRoute(<DocumentValidationPage token="ITI-VALID-2026" />);

    expect(await screen.findByText(/documento clínico autêntico/i)).toBeInTheDocument();
    expect(screen.getByText(/selo icp-brasil \/ iti/i)).toBeInTheDocument();
    expect(screen.getByText("M*** S***")).toBeInTheDocument();
    expect(screen.getByText("CPF: ***.456.789-**")).toBeInTheDocument();
    expect(screen.getByText("Dr. Eduardo Rocha")).toBeInTheDocument();
    expect(screen.getByText("CRM 123456/SP")).toBeInTheDocument();
    expect(screen.getByText(/15\/11\/2026, 15:30/)).toBeInTheDocument();
    expect(screen.getByText(/amoxicilina · 500mg/i)).toBeInTheDocument();
  });

  it("permite digitar código manualmente e exibe erro claro em resposta 404", async () => {
    server.use(
      handleValidarDocumentoApiV1DocumentsValidateTokenValidacaoGet(() => {
        return HttpResponse.json(
          {
            type: "about:blank",
            title: "Not Found",
            status: 404,
            detail: "Documento não localizado para o token informado.",
          },
          { status: 404 },
        );
      }),
    );

    renderValidationRoute(<DocumentValidationPage />);
    const user = userEvent.setup();

    await user.type(
      await screen.findByLabelText(/código ou token de validação/i),
      "TOKEN-INEXISTENTE",
    );
    await user.click(screen.getByRole("button", { name: /validar documento/i }));

    expect(
      await screen.findByText(/documento não encontrado ou código inválido/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/nenhum documento clínico foi localizado para o código informado/i),
    ).toBeInTheDocument();
  });

  it("exibe rótulo unificado para RECEITA_CONTROLE_ESPECIAL_C1", async () => {
    server.use(
      handleValidarDocumentoApiV1DocumentsValidateTokenValidacaoGet({
        body: {
          documento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b71",
          tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
          status_documento: "ASSINADO",
          sha256_hash: "b3f4b5c6d7e8",
          assinado_em: "2026-11-15T18:00:00Z",
          emissor_medico_nome: "Dra. Carla Mendes",
          emissor_medico_crm: "654321",
          emissor_medico_uf: "RJ",
          organizacao_nome: "UBS Sul",
          paciente_nome_mascarado: "J*** P***",
          paciente_cpf_mascarado: "***.111.222-**",
          assinatura_digital_valida: true,
          conformidade_icp_brasil: true,
          itens: [],
        },
      }),
    );

    renderValidationRoute(<DocumentValidationPage token="ITI-C1-2026" />);

    expect(
      await screen.findByText(/receita de controle especial \(portaria 344\/98\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/15\/11\/2026, 18:00/)).toBeInTheDocument();
  });
});
