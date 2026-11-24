import { QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { clearAccessToken, setAccessToken } from "@/lib/auth-token";
import { server } from "@/mocks/server";
import { createTestQueryClient, renderWithProviders } from "@/test/utils";
import { DoctorWorkstation } from "../components/doctor-workstation";
import { DoctorWorkstationPage } from "../pages/doctor-workstation-page";
import {
  createAssinarDocumentoResponse,
  createChamarProximoResponse,
  createDocumentoClinicoResponse,
  createEvolucaoSoapResponse,
  createLiveKitTokenResponse,
  createPainelTelemetriaResponse,
  createProntuarioResponse,
  createTmaStatusResponse,
  MOCK_ATENDIMENTO_ID,
  MOCK_DOC_ID,
} from "./fixtures";

describe("Doctor Workstation Integration Tests (US-09, US-10, CFM 2.314, RN06)", () => {
  beforeAll(async () => {
    // Pré-carrega o chunk lazy WebRTC para eliminar timeouts intermitentes no IT-DOC-02 em CI/JSDOM
    await import("../components/livekit-media-adapter");
  });

  afterEach(() => {
    vi.useRealTimers();
    clearAccessToken();
  });

  beforeEach(() => {
    // Configura os handlers padrão para teleconsulta
    server.use(
      http.post("*/api/v1/fila/chamar-proximo", () => {
        return HttpResponse.json(createChamarProximoResponse());
      }),
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/livekit/token`, () => {
        return HttpResponse.json(createLiveKitTokenResponse());
      }),
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        return HttpResponse.json(createProntuarioResponse());
      }),
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/soap`, () => {
        return HttpResponse.json(createEvolucaoSoapResponse());
      }),
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/soap`, () => {
        return HttpResponse.json(createEvolucaoSoapResponse());
      }),
      http.post(
        `*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prescriptions/validate`,
        async ({ request }) => {
          const body = (await request.json()) as { medicamento: string };
          if (
            body.medicamento.toLowerCase().includes("zolpidem") ||
            body.medicamento.toLowerCase().includes("clonazepam")
          ) {
            return HttpResponse.json(
              {
                status: 422,
                title: "Prescrição Proibida em Telemedicina",
                detail: `O medicamento '${body.medicamento}' exige talonário físico (Listas A/B da Portaria 344/98) e é proibido em telemedicina.`,
                code: "PRESCRICAO_FISICA_OBRIGATORIA",
              },
              { status: 422 },
            );
          }
          return HttpResponse.json({
            status: "PERMITIDO",
            medicamento: body.medicamento,
            mensagem: "Substância autorizada para prescrição digital em telemedicina.",
          });
        },
      ),
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents`, () => {
        return HttpResponse.json(createDocumentoClinicoResponse(), { status: 201 });
      }),
      http.post(
        `*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents/${MOCK_DOC_ID}/sign`,
        () => {
          return HttpResponse.json(createAssinarDocumentoResponse());
        },
      ),
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/tma-status`, () => {
        return HttpResponse.json(createTmaStatusResponse());
      }),
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/finalize`, () => {
        return HttpResponse.json({
          status: "FINALIZADO",
          atendimento_id: MOCK_ATENDIMENTO_ID,
          is_finalizado: true,
          mensagem: "Consulta finalizada com sucesso. Registros PEP travados de forma imutável.",
        });
      }),
    );
  });

  it("IT-DOC-01: Estado inicial sem atendimento exibe aviso, telemetria da fila e botão para chamar próximo", async () => {
    renderWithProviders(
      <DoctorWorkstation
        medicoId="018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e"
        medicoNome="Dra. Helena Costa"
        crmUf="98765/MG"
      />,
    );

    expect(screen.getByText(/dra\. helena costa/i)).toBeInTheDocument();
    expect(screen.queryByText(/dr\. eduardo rocha/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /chamar próximo paciente/i })).toBeInTheDocument();
    expect(screen.getByText(/nenhum atendimento clínico ativo/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("badge-pacientes-fila")).toHaveTextContent(/3 pacientes na fila/i);
    });
    expect(screen.getByText(/3 pacientes aguardando/i)).toBeInTheDocument();
  });

  it("IT-DOC-02: Chamar próximo aloca paciente e monta a workstation em 3 colunas contínuas sem strings hardcoded", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <DoctorWorkstation
        medicoId="018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e"
        medicoNome="Dra. Helena Costa"
        crmUf="98765/MG"
      />,
    );

    const btnChamar = screen.getByRole("button", { name: /chamar próximo paciente/i });
    await user.click(btnChamar);

    // Deve carregar as 3 seções sem troca de abas
    await waitFor(() => {
      expect(
        screen.getByRole("region", { name: /videoconferência e identificação/i }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("region", { name: /prontuário médico e histórico/i }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("region", { name: /evolução clínica e prescrição/i }),
    ).toBeInTheDocument();

    // LiveKit SFU conectado
    await waitFor(
      () => {
        expect(screen.getByText(/livekit sfu conectado/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    // Identificação real/protegida derivada sem hardcoded "Juliana Silva" / "123.***.***-00"
    expect(screen.queryByText(/juliana silva/i)).not.toBeInTheDocument();
    expect(screen.queryByText("123.***.***-00")).not.toBeInTheDocument();
    expect(screen.getAllByText(/paciente #018f3a5b/i).length).toBeGreaterThan(0);
    // Notas SOAP carregadas
    expect(screen.getByLabelText(/subjetivo \(s\)/i)).toBeInTheDocument();
    // TMA dentro do SLA esperado (fixture com 5 minutos decorridos, sem falso estouro)
    expect(screen.getByText(/TMA:\s*05:0\d \/ 15m/i)).toBeInTheDocument();
    expect(screen.queryByText(/teleconsulta preservada sob rn06/i)).not.toBeInTheDocument();
  });

  it("IT-DOC-03: Salva evolução clínica SOAP com sucesso", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/subjetivo \(s\)/i)).toBeInTheDocument();
    });

    const anamneseInput = screen.getByLabelText(/subjetivo \(s\)/i);
    await user.clear(anamneseInput);
    await user.type(anamneseInput, "Paciente com tosse persistente e febre baixa.");

    const condutaInput = screen.getByLabelText(/plano \(p\)/i);
    await user.clear(condutaInput);
    await user.type(condutaInput, "Solicitado hemograma e raio-x de tórax.");

    const btnSalvar = screen.getByRole("button", { name: /salvar evolução soap/i });
    await user.click(btnSalvar);

    await waitFor(() => {
      expect(screen.getByText(/evolução clínica soap salva com sucesso/i)).toBeInTheDocument();
    });
  });

  it("IT-DOC-04: Bloqueia substância controlada da Portaria 344/98 com mensagem legal de erro", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/medicamento \/ princípio ativo/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/medicamento \/ princípio ativo/i), "Zolpidem 10mg");
    await user.type(screen.getByLabelText(/dosagem/i), "10mg");
    await user.type(screen.getByLabelText(/posologia/i), "1 cp ao deitar");

    const btnAdicionar = screen.getByRole("button", { name: /adicionar à receita/i });
    await user.click(btnAdicionar);

    // Alerta em vermelho com offending value interpolado
    await waitFor(() => {
      expect(screen.getByText(/bloqueio sanitário legal/i)).toBeInTheDocument();
      expect(
        screen.getByText(/o medicamento 'zolpidem 10mg' exige talonário físico/i),
      ).toBeInTheDocument();
    });

    // Não deve adicionar item na lista
    expect(screen.getByText(/itens da prescrição \(0\)/i)).toBeInTheDocument();
  });

  it("IT-DOC-05: Adiciona medicamento permitido na receita (Amoxicilina)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/medicamento \/ princípio ativo/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/medicamento \/ princípio ativo/i), "Amoxicilina 500mg");
    await user.type(screen.getByLabelText(/dosagem/i), "500mg");
    await user.type(screen.getByLabelText(/posologia/i), "1 cápsula de 8/8h por 7 dias");

    await user.click(screen.getByRole("button", { name: /adicionar à receita/i }));

    await waitFor(() => {
      expect(screen.getByText(/itens da prescrição \(1\)/i)).toBeInTheDocument();
      expect(screen.getByText(/amoxicilina 500mg/i)).toBeInTheDocument();
    });
  });

  it("IT-DOC-06: Gate CFM 2.314 bloqueia emissão de receita até conferência de identidade em vídeo", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/medicamento \/ princípio ativo/i)).toBeInTheDocument();
    });

    // Adiciona medicamento
    await user.type(screen.getByLabelText(/medicamento \/ princípio ativo/i), "Amoxicilina 500mg");
    await user.type(screen.getByLabelText(/dosagem/i), "500mg");
    await user.type(screen.getByLabelText(/posologia/i), "1 cp 8/8h");
    await user.click(screen.getByRole("button", { name: /adicionar à receita/i }));

    await waitFor(() => {
      expect(screen.getByText(/itens da prescrição \(1\)/i)).toBeInTheDocument();
    });

    // Botão de emitir prescrição DEVE estar desabilitado enquanto identidade não for confirmada
    const btnEmitir = screen.getByRole("button", { name: /emitir prescrição digital/i });
    expect(btnEmitir).toBeDisabled();
    expect(
      screen.getByText(
        /a emissão da receita digital está bloqueada até a conclusão da conferência visual/i,
      ),
    ).toBeInTheDocument();

    // Confirmar conferência de RG
    const btnConfirmarIdentidade = screen.getByRole("button", {
      name: /confirmar conferência visual de identidade/i,
    });
    await user.click(btnConfirmarIdentidade);

    await waitFor(() => {
      expect(screen.getByText(/identidade confirmada/i)).toBeInTheDocument();
    });

    // Agora o botão de emissão DEVE estar habilitado
    expect(btnEmitir).toBeEnabled();
  });

  it("IT-DOC-07: Fluxo completo de emissão de receita, assinatura ICP-Brasil e conclusão imutável", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /confirmar conferência visual/i }),
      ).toBeInTheDocument();
    });

    // 1. Confirmar identidade CFM 2.314
    await user.click(screen.getByRole("button", { name: /confirmar conferência visual/i }));
    await waitFor(() => expect(screen.getByText(/identidade confirmada/i)).toBeInTheDocument());

    // 2. Adicionar medicamento
    await user.type(screen.getByLabelText(/medicamento \/ princípio ativo/i), "Amoxicilina 500mg");
    await user.type(screen.getByLabelText(/dosagem/i), "500mg");
    await user.type(screen.getByLabelText(/posologia/i), "1 cp 8/8h");
    await user.click(screen.getByRole("button", { name: /adicionar à receita/i }));

    await waitFor(() => expect(screen.getByText(/itens da prescrição \(1\)/i)).toBeInTheDocument());

    // 3. Emitir prescrição digital
    await user.click(screen.getByRole("button", { name: /emitir prescrição digital/i }));

    await waitFor(() => {
      expect(screen.getByText(/receita digital #.*gerada com sucesso/i)).toBeInTheDocument();
    });

    // 4. Abrir modal de conclusão
    await user.click(screen.getByRole("button", { name: /concluir atendimento & assinar/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /concluir atendimento clínico/i }),
      ).toBeInTheDocument();
    });

    // 5. Inserir credencial PSC e assinar
    const tokenInput = screen.getByLabelText(/token oauth2 \/ otp do psc/i);
    await user.type(tokenInput, "psc-valid-token-123");

    await user.click(screen.getByRole("button", { name: /assinar documento digitalmente/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/documento clínico assinado digitalmente com sucesso/i),
      ).toBeInTheDocument();
    });

    // 6. Confirmar encerramento e travar PEP
    await user.click(screen.getByRole("button", { name: /confirmar encerramento e travar pep/i }));

    // Modal fecha e banner de imutabilidade é renderizado
    await waitFor(() => {
      expect(
        screen.getByText(/atendimento concluído com sucesso.*congelados em modo imutável/i),
      ).toBeInTheDocument();
    });

    // Botão de concluir atendimento não deve mais existir
    expect(
      screen.queryByRole("button", { name: /concluir atendimento & assinar/i }),
    ).not.toBeInTheDocument();
  });

  it("IT-DOC-08: Fila vazia exibe aviso amigável sem quebrar o estado", async () => {
    server.use(
      http.get("*/api/v1/telemetria/painel", () => {
        return HttpResponse.json(createPainelTelemetriaResponse({ total_pacientes_fila: 0 }));
      }),
      http.post("*/api/v1/fila/chamar-proximo", () => {
        return HttpResponse.json({
          alocado: false,
          mensagem: "Fila vazia. Não há pacientes aguardando atendimento no momento.",
        });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await waitFor(() => {
      expect(screen.getByTestId("badge-pacientes-fila")).toHaveTextContent(/fila vazia \(0\)/i);
    });
    expect(screen.getByText(/não há pacientes aguardando no momento/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        /não há pacientes aguardando atendimento no momento/i,
      );
    });

    // Permanece no estado inicial
    expect(screen.getByText(/nenhum atendimento clínico ativo/i)).toBeInTheDocument();
  });

  it("IT-DOC-09: Exceção médica de emergência destrava o gate CFM 2.314 com justificativa", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/exceção médica de emergência/i)).toBeInTheDocument();
    });

    // Seleciona exceção médica
    await user.click(screen.getByLabelText(/exceção médica de emergência/i));

    const justificativaInput = screen.getByLabelText(/justificativa formal da exceção clínica/i);
    await user.type(justificativaInput, "Paciente inconsciente em estado grave na emergência");

    await user.click(
      screen.getByRole("button", { name: /confirmar conferência visual de identidade/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/liberado por exceção ética de urgência \/ emergência/i),
      ).toBeInTheDocument();
      expect(screen.getByText(/identidade confirmada/i)).toBeInTheDocument();
    });
  });

  it("IT-DOC-10: Estouro de TMA exibe aviso passivo sem desconectar videoconferência (RN06)", async () => {
    // Simula chamada alocada com início há 16 minutos (960 segundos > 900)
    server.use(
      http.post("*/api/v1/fila/chamar-proximo", () => {
        return HttpResponse.json(
          createChamarProximoResponse({
            chamada_iniciada_em: new Date(Date.now() - 960 * 1000).toISOString(),
            ttl_segundos: 900,
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

    const btnChamar = screen.getByRole("button", { name: /chamar próximo paciente/i });
    await user.click(btnChamar);

    // O aviso passivo deve ser exibido com TMA ultrapassado
    await waitFor(() => {
      expect(screen.getByText(/teleconsulta preservada sob rn06/i)).toBeInTheDocument();
    });

    // A videoconferência continua plenamente conectada
    await waitFor(
      () => {
        expect(screen.getByText(/livekit sfu conectado/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
  });

  it("IT-DOC-11: Desconecta a sessão médica por inatividade clínica (Auto-Logout)", async () => {
    vi.useFakeTimers();
    const handleLogout = vi.fn();
    renderWithProviders(<DoctorWorkstation onLogout={handleLogout} idleTimeoutMs={5000} />);

    // Antes do timeout, onLogout não foi chamado
    expect(handleLogout).not.toHaveBeenCalled();

    // Avança o timer além do limite de inatividade dentro de act() para drenar promises do React 19
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    // onLogout deve ter sido invocado automaticamente
    expect(handleLogout).toHaveBeenCalledTimes(1);
  });

  it("IT-DOC-12: DoctorWorkstationPage utiliza token atualizado pós-refresh sem congelar no render e limpa QueryClient no logout", async () => {
    setAccessToken("expired-initial-doctor-token");
    const capturedAuthHeaders: Array<string | null> = [];

    server.use(
      http.get("*/api/v1/telemetria/painel", ({ request }) => {
        capturedAuthHeaders.push(request.headers.get("Authorization"));
        return HttpResponse.json(createPainelTelemetriaResponse());
      }),
      http.post("*/api/v1/fila/chamar-proximo", ({ request }) => {
        capturedAuthHeaders.push(request.headers.get("Authorization"));
        return HttpResponse.json(createChamarProximoResponse());
      }),
      http.post("*/api/v1/auth/logout", () => {
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const queryClient = createTestQueryClient();
    const testRootRoute = createRootRoute({
      component: () => (
        <QueryClientProvider client={queryClient}>
          <Outlet />
        </QueryClientProvider>
      ),
    });
    const medicoRouteTest = createRoute({
      getParentRoute: () => testRootRoute,
      path: "/medico",
      component: () => (
        <DoctorWorkstationPage
          doctorSession={{
            medicoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
            medicoNome: "Dr. Eduardo Rocha",
            crmUf: "123456/SP",
            identificador: "123456/SP",
          }}
        />
      ),
    });
    const loginRouteTest = createRoute({
      getParentRoute: () => testRootRoute,
      path: "/interno/login",
      component: () => <div>Login Interno Mock</div>,
    });
    const router = createRouter({
      routeTree: testRootRoute.addChildren([medicoRouteTest, loginRouteTest]),
      history: createMemoryHistory({ initialEntries: ["/medico"] }),
    });

    render(<RouterProvider router={router as never} />);

    // Carregamento inicial usa token inicial e popula cache
    await waitFor(() => {
      expect(screen.getByTestId("badge-pacientes-fila")).toHaveTextContent(/3 pacientes na fila/i);
    });
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);

    // Simula rotação via silentRefreshToken() sem remountar a página
    setAccessToken("rotated-fresh-doctor-token");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(capturedAuthHeaders).toContain("Bearer rotated-fresh-doctor-token");
    });

    // Logout deve limpar todo o QueryClient para evitar vazamento entre sessões clínicas
    await user.click(screen.getByRole("button", { name: /sair do plantão/i }));

    await waitFor(() => {
      expect(screen.getByText("Login Interno Mock")).toBeInTheDocument();
      expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    });
  });

  it("IT-DOC-13: Troca Paciente A -> Paciente B remonta ConsultationEncounterProvider sem vazar documentoAssinado ou badge CFM", async () => {
    const ATENDIMENTO_A = MOCK_ATENDIMENTO_ID;
    const ATENDIMENTO_B = "018f3a5b-9999-4b2c-8b2c-018f3a5b7b99";
    const PACIENTE_A = "11111111-1111-4b2c-8b2c-018f3a5b7b11";
    const PACIENTE_B = "22222222-2222-4b2c-8b2c-018f3a5b7b22";
    let callCount = 0;

    server.use(
      http.post("*/api/v1/fila/chamar-proximo", () => {
        callCount += 1;
        if (callCount === 1) {
          return HttpResponse.json(
            createChamarProximoResponse({
              atendimento_id: ATENDIMENTO_A,
              paciente_id: PACIENTE_A,
            }),
          );
        }
        return HttpResponse.json(
          createChamarProximoResponse({
            atendimento_id: ATENDIMENTO_B,
            paciente_id: PACIENTE_B,
          }),
        );
      }),
      http.post(`*/api/v1/consultations/${ATENDIMENTO_B}/livekit/token`, () =>
        HttpResponse.json(createLiveKitTokenResponse({ room_name: `room_${ATENDIMENTO_B}` })),
      ),
      http.get(`*/api/v1/consultations/${ATENDIMENTO_B}/prontuario`, () =>
        HttpResponse.json(createProntuarioResponse({ atendimento_id: ATENDIMENTO_B })),
      ),
      http.get(`*/api/v1/consultations/${ATENDIMENTO_B}/soap`, () =>
        HttpResponse.json(createEvolucaoSoapResponse({ atendimento_id: ATENDIMENTO_B })),
      ),
      http.get(`*/api/v1/consultations/${ATENDIMENTO_B}/tma-status`, () =>
        HttpResponse.json(createTmaStatusResponse()),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <DoctorWorkstation
        medicoId="018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e"
        medicoNome="Dra. Helena Costa"
        crmUf="98765/MG"
      />,
    );

    // 1. Aloca Paciente A, confirma identidade CFM e assina documento no modal
    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /confirmar conferência visual/i }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /confirmar conferência visual/i }));
    expect(await screen.findByText(/identidade confirmada/i)).toBeInTheDocument();

    // Emite e assina documento para Paciente A
    await user.type(screen.getByLabelText(/medicamento \/ princípio ativo/i), "Dipirona 500mg");
    await user.type(screen.getByLabelText(/dosagem/i), "500mg");
    await user.type(screen.getByLabelText(/posologia/i), "1 cp 6/6h");
    await user.click(screen.getByRole("button", { name: /adicionar à receita/i }));
    await waitFor(() => expect(screen.getByText(/itens da prescrição \(1\)/i)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /emitir prescrição digital/i }));
    await waitFor(() =>
      expect(screen.getByText(/receita.*gerada com sucesso/i)).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /concluir atendimento & assinar/i }));
    const tokenInput = await screen.findByLabelText(/token oauth2 \/ otp do psc/i);
    await user.type(tokenInput, "psc-token-paciente-a");
    await user.click(screen.getByRole("button", { name: /assinar documento digitalmente/i }));
    await waitFor(() =>
      expect(
        screen.getByText(/documento clínico assinado digitalmente com sucesso/i),
      ).toBeInTheDocument(),
    );
    await user.keyboard("{Escape}");

    // 2. Troca para Paciente B chamando o próximo paciente
    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));

    await waitFor(() => {
      expect(screen.queryByText(/paciente #11111111/i)).not.toBeInTheDocument();
      expect(screen.getAllByText(/paciente #22222222/i).length).toBeGreaterThan(0);
      expect(screen.queryByText(/identidade confirmada/i)).not.toBeInTheDocument();
      expect(screen.getByText(/conferência obrigatória/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /emitir prescrição digital/i })).toBeDisabled();
  });

  it("IT-DOC-14: SoapEditor propaga shouldValidate e shouldDirty no handleCid10Change ao digitar CID-10", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation medicoNome="Dra. Helena Costa" crmUf="98765/MG" />);

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));
    const cidInput = await screen.findByLabelText(/cid-10/i);

    await user.type(screen.getByLabelText(/subjetivo \(s\)/i), "Tosse há 3 dias");
    await user.type(screen.getByLabelText(/plano \(p\)/i), "Repouso e hidratação");

    await user.type(cidInput, "123");
    await user.click(screen.getByRole("button", { name: /salvar evolução soap/i }));
    expect(await screen.findByText(/código cid-10 inválido/i)).toBeInTheDocument();

    await user.clear(cidInput);
    await user.type(cidInput, "j02.9");

    await waitFor(() => {
      expect(cidInput).toHaveValue("J02.9");
      expect(screen.queryByText(/código cid-10 inválido/i)).not.toBeInTheDocument();
    });
  });

  it("IT-DOC-15: DoctorWorkstationPage conecta onAtendimentoIniciado da agenda abrindo LiveKit + PEP", async () => {
    const SCHEDULED_ATEND_ID = "018f3a5b-7777-4b2c-8b2c-018f3a5b7777";
    const SCHEDULED_PAC_ID = "018f3a5b-8888-4b2c-8b2c-018f3a5b8888";

    server.use(
      http.get("*/api/v1/telemetria/painel", () =>
        HttpResponse.json(createPainelTelemetriaResponse()),
      ),
      http.post(`*/api/v1/consultations/${SCHEDULED_ATEND_ID}/livekit/token`, () =>
        HttpResponse.json(createLiveKitTokenResponse({ room_name: `room_${SCHEDULED_ATEND_ID}` })),
      ),
      http.get(`*/api/v1/consultations/${SCHEDULED_ATEND_ID}/prontuario`, () =>
        HttpResponse.json(createProntuarioResponse({ atendimento_id: SCHEDULED_ATEND_ID })),
      ),
      http.get(`*/api/v1/consultations/${SCHEDULED_ATEND_ID}/soap`, () =>
        HttpResponse.json(createEvolucaoSoapResponse({ atendimento_id: SCHEDULED_ATEND_ID })),
      ),
      http.get(`*/api/v1/consultations/${SCHEDULED_ATEND_ID}/tma-status`, () =>
        HttpResponse.json(createTmaStatusResponse()),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <DoctorWorkstationPage
        doctorSession={{
          medicoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
          medicoNome: "Dra. Helena Costa",
          crmUf: "98765/MG",
          identificador: "98765/MG",
        }}
        renderSchedulePanel={(onAtendimentoIniciado) => (
          <button
            type="button"
            onClick={() =>
              onAtendimentoIniciado?.({
                id: "ag-01",
                paciente_id: SCHEDULED_PAC_ID,
                profissional_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
                especialidade: "PSICOLOGIA",
                slot_inicio: "2026-11-24T14:00:00Z",
                slot_fim: "2026-11-24T14:50:00Z",
                status: "EM_ATENDIMENTO",
                observacoes: "Retorno agendado eMulti",
                atendimento_id: SCHEDULED_ATEND_ID,
                criado_em: "2026-11-20T10:00:00Z",
                atualizado_em: "2026-11-24T14:00:00Z",
              })
            }
          >
            Acionar Agendamento Teste
          </button>
        )}
      />,
    );

    await user.click(screen.getByRole("button", { name: /acionar agendamento teste/i }));

    await waitFor(() => {
      expect(screen.getByText(/livekit sfu conectado/i)).toBeInTheDocument();
      expect(screen.getByText(/retorno agendado emulti/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/subjetivo \(s\)/i)).toBeInTheDocument();
    });
  });

  it("IT-DOC-16: Troca Paciente A -> Paciente B limpa token/sala LiveKit de A imediatamente e em falha HTTP 500 para B", async () => {
    const ATENDIMENTO_A = MOCK_ATENDIMENTO_ID;
    const ATENDIMENTO_B = "018f3a5b-9999-4b2c-8b2c-018f3a5b7b99";
    const PACIENTE_A = "11111111-1111-4b2c-8b2c-018f3a5b7b11";
    const PACIENTE_B = "22222222-2222-4b2c-8b2c-018f3a5b7b22";
    const ROOM_A = `room_${ATENDIMENTO_A}`;
    let callCount = 0;
    const tokenBDeferred: { resolve: (() => void) | null } = { resolve: null };

    server.use(
      http.post("*/api/v1/fila/chamar-proximo", () => {
        callCount += 1;
        if (callCount === 1) {
          return HttpResponse.json(
            createChamarProximoResponse({
              atendimento_id: ATENDIMENTO_A,
              paciente_id: PACIENTE_A,
            }),
          );
        }
        return HttpResponse.json(
          createChamarProximoResponse({
            atendimento_id: ATENDIMENTO_B,
            paciente_id: PACIENTE_B,
          }),
        );
      }),
      http.post(`*/api/v1/consultations/${ATENDIMENTO_A}/livekit/token`, () =>
        HttpResponse.json(
          createLiveKitTokenResponse({
            room_name: ROOM_A,
            token: "livekit-token-a",
          }),
        ),
      ),
      http.post(
        `*/api/v1/consultations/${ATENDIMENTO_B}/livekit/token`,
        () =>
          new Promise<Response>((resolve) => {
            tokenBDeferred.resolve = () =>
              resolve(HttpResponse.json({ detail: "Falha ao emitir token SFU" }, { status: 500 }));
          }),
      ),
      http.get(`*/api/v1/consultations/${ATENDIMENTO_B}/prontuario`, () =>
        HttpResponse.json(createProntuarioResponse({ atendimento_id: ATENDIMENTO_B })),
      ),
      http.get(`*/api/v1/consultations/${ATENDIMENTO_B}/soap`, () =>
        HttpResponse.json(createEvolucaoSoapResponse({ atendimento_id: ATENDIMENTO_B })),
      ),
      http.get(`*/api/v1/consultations/${ATENDIMENTO_B}/tma-status`, () =>
        HttpResponse.json(createTmaStatusResponse()),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <DoctorWorkstation
        medicoId="018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e"
        medicoNome="Dra. Helena Costa"
        crmUf="98765/MG"
      />,
    );

    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));
    await waitFor(() => {
      expect(screen.getByText(ROOM_A)).toBeInTheDocument();
      expect(screen.getByText(/livekit sfu conectado/i)).toBeInTheDocument();
    });

    // Troca para Paciente B enquanto emissão do token LiveKit para B ainda está pendente
    await user.click(screen.getByRole("button", { name: /chamar próximo paciente/i }));
    await waitFor(() => {
      expect(screen.getByText(`room_${ATENDIMENTO_B}`)).toBeInTheDocument();
    });
    expect(screen.queryByText(ROOM_A)).not.toBeInTheDocument();
    expect(screen.queryByText(/livekit sfu conectado/i)).not.toBeInTheDocument();
    expect(screen.getByText(/conectando ao livekit/i)).toBeInTheDocument();

    // Emissão de B falha com HTTP 500 — sala e status de A não podem reaparecer
    tokenBDeferred.resolve?.();
    await waitFor(() => {
      expect(screen.queryByText(ROOM_A)).not.toBeInTheDocument();
      expect(screen.queryByText(/livekit sfu conectado/i)).not.toBeInTheDocument();
      expect(screen.getByText(`room_${ATENDIMENTO_B}`)).toBeInTheDocument();
    });
  });
});
