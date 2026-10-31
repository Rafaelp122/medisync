import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/utils";
import { EnriquecimentoFase2Form } from "../components/enriquecimento-fase2-form";
import { MOCK_CEP_VALIDO, MOCK_INTAKE_TOKEN, MOCK_PACIENTE_ID } from "./fixtures";

describe("EnriquecimentoFase2Form (Integração de Tela - RF-02, US-03)", () => {
  it("IT-ONB-05: Preenchimento com autopreenchimento dinâmico de endereço via ViaCEP", async () => {
    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, getByRole } = renderWithProviders(
      <EnriquecimentoFase2Form
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_INTAKE_TOKEN}
        onConcluido={handleConcluido}
      />,
    );

    // Nome da mãe
    await user.type(getByLabelText(/nome completo da mãe/i), "Maria Aparecida Silva");

    // Selecionar sexo biológico feminino
    const radioF = getByRole("radio", { name: /feminino/i });
    await user.click(radioF);
    expect(radioF).toBeChecked();

    // Digitar CEP
    const cepInput = getByLabelText(/cep/i);
    await user.type(cepInput, MOCK_CEP_VALIDO);

    // Verificar se autopreenchimento do ViaCEP populou os campos
    await waitFor(() => {
      expect(getByLabelText(/logradouro/i)).toHaveValue("Avenida Paulista");
      expect(getByLabelText(/bairro/i)).toHaveValue("Bela Vista");
      expect(getByLabelText(/cidade/i)).toHaveValue("São Paulo");
      expect(getByLabelText(/uf/i)).toHaveValue("SP");
    });

    // Preencher número
    await user.type(getByLabelText(/número/i), "1000");

    // Selecionar alergia
    const dipironaBtn = getByRole("button", { name: /^dipirona$/i });
    expect(dipironaBtn).toHaveAttribute("aria-pressed", "false");
    await user.click(dipironaBtn);
    expect(dipironaBtn).toHaveAttribute("aria-pressed", "true");

    // Submeter
    await user.click(getByRole("button", { name: /concluir enriquecimento/i }));

    await waitFor(() => {
      expect(handleConcluido).toHaveBeenCalled();
    });
  });

  it("IT-ONB-06: Resiliência em caso de CEP não localizado, permitindo digitação manual", async () => {
    const user = userEvent.setup();
    const handleConcluido = vi.fn();

    const { getByLabelText, findByText } = renderWithProviders(
      <EnriquecimentoFase2Form pacienteId={MOCK_PACIENTE_ID} onConcluido={handleConcluido} />,
    );

    await user.type(getByLabelText(/nome completo da mãe/i), "Maria Silva");
    await user.type(getByLabelText(/cep/i), "99999999");

    // Deve exibir aviso amigável
    expect(await findByText(/cep não localizado/i)).toBeInTheDocument();

    // Campos de logradouro permanecem desbloqueados para preenchimento manual
    const logradouroInput = getByLabelText(/logradouro/i);
    expect(logradouroInput).toBeEnabled();
    await user.type(logradouroInput, "Rua do Interior");
    expect(logradouroInput).toHaveValue("Rua do Interior");
  });

  it("IT-ONB-07: Clique em 'Completar mais tarde' aciona callback onPular sem bloquear o paciente", async () => {
    const user = userEvent.setup();
    const handlePular = vi.fn();

    const { getByRole } = renderWithProviders(
      <EnriquecimentoFase2Form
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_INTAKE_TOKEN}
        onConcluido={vi.fn()}
        onPular={handlePular}
      />,
    );

    const btnPular = getByRole("button", { name: /completar mais tarde/i });
    expect(btnPular).toBeInTheDocument();
    await user.click(btnPular);

    expect(handlePular).toHaveBeenCalledTimes(1);
  });
});
