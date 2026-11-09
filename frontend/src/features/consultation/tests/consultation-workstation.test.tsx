import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { DoctorWorkstation } from "../components/doctor-workstation";
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
  afterEach(() => {
    vi.useRealTimers();
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
    renderWithProviders(<DoctorWorkstation />);

    expect(screen.getByText(/dr\. eduardo rocha/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /chamar próximo paciente/i })).toBeInTheDocument();
    expect(screen.getByText(/nenhum atendimento clínico ativo/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("badge-pacientes-fila")).toHaveTextContent(/3 pacientes na fila/i);
    });
    expect(screen.getByText(/3 pacientes aguardando/i)).toBeInTheDocument();
  });

  it("IT-DOC-02: Chamar próximo aloca paciente e monta a workstation em 3 colunas contínuas", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DoctorWorkstation />);

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
    // Identificação do paciente
    expect(screen.getAllByText(/juliana silva/i).length).toBeGreaterThan(0);
    // Notas SOAP carregadas
    expect(screen.getByLabelText(/subjetivo \(s\)/i)).toBeInTheDocument();
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

    // Avança o timer além do limite de inatividade
    await vi.advanceTimersByTimeAsync(5000);

    // onLogout deve ter sido invocado automaticamente
    expect(handleLogout).toHaveBeenCalledTimes(1);
  });
});
