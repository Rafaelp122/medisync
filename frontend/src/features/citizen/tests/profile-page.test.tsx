import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleCadastrarDependenteApiV1PacientesIdDependentesPost,
  handleListarDependentesApiV1PacientesIdDependentesGet,
} from "@/api/generated/msw.gen";
import type { DependenteDetalheResponse } from "@/api/generated/types.gen";
import { settings } from "@/config/settings";
import { ProfilePage } from "@/features/citizen/pages/profile-page";
import {
  MOCK_CITIZEN_SESSION,
  renderCitizenRoute,
} from "@/features/citizen/tests/test-router-helper";
import { server } from "@/mocks/server";

describe("ProfilePage (/perfil)", () => {
  let dependentesDb: DependenteDetalheResponse[] = [];

  beforeEach(() => {
    sessionStorage.clear();
    dependentesDb = [
      {
        id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b61",
        titular_id: MOCK_CITIZEN_SESSION.pacienteId,
        dependente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b62",
        grau_parentesco: "FILHO",
        nome_completo: "Pedro Silva",
        data_nascimento: "2018-05-14",
        cpf: null,
        cns: null,
        vinculado_em: "2026-11-01T10:00:00Z",
      },
    ];

    server.use(
      handleListarDependentesApiV1PacientesIdDependentesGet(() => {
        return HttpResponse.json(dependentesDb);
      }),
      handleCadastrarDependenteApiV1PacientesIdDependentesPost(async ({ request }) => {
        const body = await request.json();
        const novo: DependenteDetalheResponse = {
          id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b63",
          titular_id: MOCK_CITIZEN_SESSION.pacienteId,
          dependente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b64",
          grau_parentesco: body.grau_parentesco,
          nome_completo: body.nome_completo ?? null,
          data_nascimento: body.data_nascimento ?? "2020-01-10",
          cpf: body.cpf ?? null,
          cns: body.cns ?? null,
          vinculado_em: "2026-11-16T00:00:00Z",
        };
        dependentesDb = [...dependentesDb, novo];
        return HttpResponse.json(
          {
            id: novo.id,
            titular_id: novo.titular_id,
            dependente_id: novo.dependente_id,
            grau_parentesco: novo.grau_parentesco,
            vinculado_em: novo.vinculado_em,
          },
          { status: 201 },
        );
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("lista dependentes existentes e cadastra novo dependente via formulário Zod + MSW", async () => {
    renderCitizenRoute(<ProfilePage session={MOCK_CITIZEN_SESSION} />, "/perfil");
    const user = userEvent.setup();

    expect(await screen.findByText("Pedro Silva")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/nome completo do dependente/i), "Clara Silva");
    await user.selectOptions(screen.getByLabelText(/grau de parentesco/i), "FILHO");
    await user.type(screen.getByLabelText(/data de nascimento/i), "2021-03-20");

    await user.click(screen.getByRole("button", { name: /cadastrar dependente/i }));

    expect(await screen.findByText("Clara Silva")).toBeInTheDocument();
    expect(screen.getByText(/dependente cadastrado e vinculado com sucesso/i)).toBeInTheDocument();
  });

  it("integra slot renderEnrichmentForm e mantém gestão de Passkeys sempre visível mesmo após dispensa na fila", async () => {
    sessionStorage.setItem(settings.storage.passkeyDismissed, "true");
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    renderCitizenRoute(
      <ProfilePage
        session={MOCK_CITIZEN_SESSION}
        renderEnrichmentForm={({ pacienteId, onConcluido }) => (
          <div>
            <span>Enriquecimento para {pacienteId}</span>
            <button type="button" onClick={onConcluido}>
              Concluir Enriquecimento Teste
            </button>
          </div>
        )}
      />,
      "/perfil",
    );
    const user = userEvent.setup();

    expect(
      await screen.findByText(`Enriquecimento para ${MOCK_CITIZEN_SESSION.pacienteId}`),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ativar biometria neste aparelho/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /concluir enriquecimento teste/i }));

    expect(await screen.findByText(/cadastro cfm concluído/i)).toBeInTheDocument();
  });
});
