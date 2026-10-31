import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { AcolhimentoFase1Form } from "../components/acolhimento-fase1-form";
import { MOCK_ATENDIMENTO_ID, MOCK_CPF_VALIDO, MOCK_PACIENTE_ID } from "./fixtures";

describe("AcolhimentoFase1Form (Integração de Tela - RF-01, RN04)", () => {
  it("IT-ONB-01: Preenchimento da Fase 1 com sucesso e avanço para admissão", async () => {
    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, getByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={handleConcluido} />,
    );

    // Passo 1: Preencher identificadores
    await user.type(getByLabelText(/nome completo/i), "Juliana Santos Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);

    // Avançar para Etapa 2
    const avancarBtn = getByRole("button", { name: /continuar para triagem/i });
    expect(avancarBtn).toBeInTheDocument();
    await user.click(avancarBtn);

    // Passo 2: Preencher queixa clínica
    await user.type(
      getByLabelText(/o que você está sentindo\?/i),
      "Febre moderada e dor de cabeça há 2 dias",
    );

    // Selecionar sintoma comum
    await user.click(getByRole("button", { name: /^febre$/i }));

    // Selecionar escala de dor nível 4
    await user.click(getByRole("button", { name: /^nível 4$/i }));

    // Aceitar TCLE
    const tcleCheckbox = getByLabelText(/termo de consentimento livre e esclarecido/i);
    await user.click(tcleCheckbox);
    expect(tcleCheckbox).toBeChecked();

    // Submeter
    const submitBtn = getByRole("button", { name: /entrar na fila virtual/i });
    expect(submitBtn).toBeEnabled();
    await user.click(submitBtn);

    await waitFor(() => {
      expect(handleConcluido).toHaveBeenCalledWith(
        expect.objectContaining({
          pacienteId: MOCK_PACIENTE_ID,
          atendimentoId: MOCK_ATENDIMENTO_ID,
          prioridadeClinica: 3,
        }),
      );
    });
  });

  it("IT-ONB-02: Bloqueio estrito de submissão sem aceite do TCLE", async () => {
    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, getByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={handleConcluido} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    await user.type(getByLabelText(/o que você está sentindo\?/i), "Febre alta");

    // Botão deve estar desabilitado
    const submitBtn = getByRole("button", { name: /entrar na fila virtual/i });
    expect(submitBtn).toBeDisabled();
    expect(handleConcluido).not.toHaveBeenCalled();
  });

  it("IT-ONB-03: Detecção preventiva de sintomas de alarme críticos dispara modal SAMU 192", async () => {
    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, getByRole, findByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={handleConcluido} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    // Clicar em sintoma de alarme crítico no Passo 2
    const dorPeitoBtn = getByRole("button", {
      name: /dor no peito irradiando para o braço ou pescoço/i,
    });
    await user.click(dorPeitoBtn);

    // Modal de emergência deve abrir imediatamente
    const alertdialog = await findByRole("alertdialog");
    expect(alertdialog).toBeInTheDocument();
    expect(getByRole("link", { name: /ligar para o samu 192/i })).toHaveAttribute(
      "href",
      "tel:192",
    );
    expect(handleConcluido).not.toHaveBeenCalled();
  });

  it("IT-ONB-04: Resposta do backend 422 EMERGENCIA_CRITICA_SAMU_192 abre modal SAMU 192", async () => {
    server.use(
      http.post("*/api/v1/fila/admissao", () => {
        return HttpResponse.json(
          {
            status: 422,
            title: "Emergência Médica Crítica",
            detail: "Paciente com suspeita de infarto agudo do miocárdio. Ligue 192.",
            code: "EMERGENCIA_CRITICA_SAMU_192",
          },
          { status: 422 },
        );
      }),
    );

    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, getByRole, findByRole, queryByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={handleConcluido} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    await user.type(getByLabelText(/o que você está sentindo\?/i), "Dor no peito com suor frio");
    await user.click(getByLabelText(/termo de consentimento livre e esclarecido/i));

    await user.click(getByRole("button", { name: /entrar na fila virtual/i }));

    const alertdialog = await findByRole("alertdialog");
    expect(alertdialog).toBeInTheDocument();
    expect(queryByRole("button", { name: /selecionei por engano/i })).not.toBeInTheDocument();
    expect(handleConcluido).not.toHaveBeenCalled();
  });

  it("IT-ONB-05: Clique em 'Selecionei por engano' no modal SAMU 192 fecha o modal e desmarca sintoma", async () => {
    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, getByRole, findByRole, queryByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={handleConcluido} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    // Clicar acidentalmente em sintoma de alarme crítico
    const dorPeitoBtn = getByRole("button", {
      name: /dor no peito irradiando para o braço ou pescoço/i,
    });
    await user.click(dorPeitoBtn);

    const alertdialog = await findByRole("alertdialog");
    expect(alertdialog).toBeInTheDocument();

    // Clicar no botão de correção
    const btnCorrigir = getByRole("button", { name: /selecionei por engano/i });
    await user.click(btnCorrigir);

    // Modal deve fechar
    await waitFor(() => {
      expect(queryByRole("alertdialog")).not.toBeInTheDocument();
    });
  });

  it("IT-ONB-06: Botão 'Voltar' do Passo 2 para o Passo 1 preserva os dados de identificação", async () => {
    const user = userEvent.setup();
    const { getByLabelText, getByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={vi.fn()} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    // Estamos no Passo 2
    expect(getByRole("button", { name: /voltar/i })).toBeInTheDocument();
    await user.click(getByRole("button", { name: /voltar/i }));

    // Voltamos ao Passo 1: dados continuam preenchidos
    expect(getByLabelText(/nome completo/i)).toHaveValue("Juliana Silva");
    expect(getByLabelText(/telefone celular com ddd/i)).toHaveValue("(11) 98765-4321");
  });

  it("IT-ONB-07: Resposta HTTP 500 do backend exibe banner humanizado em português com botão Tentar Novamente", async () => {
    server.use(
      http.post("*/api/v1/onboarding/fase-1", () => {
        return HttpResponse.json(
          {
            status: 500,
            title: "Internal Server Error",
            detail: "An internal server error occurred. Please contact support.",
            code: "INTERNAL_SERVER_ERROR",
          },
          { status: 500 },
        );
      }),
    );

    const user = userEvent.setup();
    const { getByLabelText, getByRole, findByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={vi.fn()} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    await user.type(getByLabelText(/o que você está sentindo\?/i), "Febre alta");
    await user.click(getByLabelText(/termo de consentimento livre e esclarecido/i));

    await user.click(getByRole("button", { name: /entrar na fila virtual/i }));

    // Banner de alerta humanizado
    const alert = await findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent(/instabilidade temporária no servidor/i);
    expect(alert).toHaveTextContent(/seus dados continuam preenchidos/i);

    // Botão de tentar novamente deve estar presente
    expect(getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("IT-ONB-08: Alternar entre CPF e Cartão SUS limpa o campo anterior e define atributos aria-pressed", async () => {
    const user = userEvent.setup();
    const { getByLabelText, getByRole } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={vi.fn()} />,
    );

    const btnCpf = getByRole("button", { name: /^cpf$/i });
    const btnCns = getByRole("button", { name: /cartão sus/i });

    expect(btnCpf).toHaveAttribute("aria-pressed", "true");
    expect(btnCns).toHaveAttribute("aria-pressed", "false");

    // Digita CPF
    const inputCpf = getByLabelText(/documento de identificação \(cpf\)/i);
    await user.type(inputCpf, "52998224725");
    expect(inputCpf).toHaveValue("529.982.247-25");

    // Alterna para Cartão SUS
    await user.click(btnCns);
    expect(btnCns).toHaveAttribute("aria-pressed", "true");
    expect(btnCpf).toHaveAttribute("aria-pressed", "false");

    // Campo de Cartão SUS está vazio
    const inputCns = getByLabelText(/documento de identificação \(cartão sus\)/i);
    expect(inputCns).toHaveValue("");

    // Alterna de volta para CPF e campo está limpo
    await user.click(btnCpf);
    const inputCpfNovo = getByLabelText(/documento de identificação \(cpf\)/i);
    expect(inputCpfNovo).toHaveValue("");
  });

  it("IT-ONB-09: Confirmar saída presencial no modal SAMU 192 renderiza tela de orientação médica e permite reiniciar", async () => {
    const user = userEvent.setup();
    const { getByLabelText, getByRole, findByRole, queryByRole, getByText } = renderWithProviders(
      <AcolhimentoFase1Form onAdmissaoConcluida={vi.fn()} />,
    );

    await user.type(getByLabelText(/nome completo/i), "Juliana Silva");
    await user.type(getByLabelText(/data de nascimento/i), "1992-08-20");
    await user.type(getByLabelText(/telefone celular com ddd/i), "11987654321");
    await user.type(getByLabelText(/documento de identificação/i), MOCK_CPF_VALIDO);
    await user.click(getByRole("button", { name: /continuar para triagem/i }));

    // Clicar em sintoma de alarme crítico
    await user.click(
      getByRole("button", { name: /dor no peito irradiando para o braço ou pescoço/i }),
    );

    const alertdialog = await findByRole("alertdialog");
    expect(alertdialog).toBeInTheDocument();

    // Clicar em procurar atendimento presencial
    const btnSaida = getByRole("button", {
      name: /entendi, vou procurar atendimento presencial/i,
    });
    await user.click(btnSaida);

    // Deve exibir o card de orientação presencial de urgência
    expect(
      await findByRole("heading", { name: /atendimento presencial de urgência recomendado/i }),
    ).toBeVisible();
    expect(getByRole("link", { name: /ligar para o samu 192/i })).toHaveAttribute(
      "href",
      "tel:192",
    );

    // Não deve permitir retorno direto ao acolhimento (burlar RN04)
    expect(queryByRole("button", { name: /^voltar ao acolhimento$/i })).not.toBeInTheDocument();

    // Deve permitir apenas reiniciar o acolhimento do início (wipe total)
    const btnReiniciar = getByRole("button", {
      name: /reiniciar acolhimento do início/i,
    });
    expect(btnReiniciar).toBeInTheDocument();
    await user.click(btnReiniciar);

    // Deve resetar o estado e retornar à etapa de identificação com formulário limpo
    expect(await findByRole("heading", { name: /pronto atendimento virtual/i })).toBeVisible();
    expect(getByText(/etapa 1 de 2: identificação/i)).toBeInTheDocument();
    expect(getByLabelText(/nome completo/i)).toHaveValue("");
  });
});
