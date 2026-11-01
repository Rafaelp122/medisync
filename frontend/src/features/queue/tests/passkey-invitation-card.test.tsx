import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/utils";
import { PasskeyInvitationCard } from "../components/passkey-invitation-card";

describe("PasskeyInvitationCard (Convite Não-Bloqueante de Biometria - US-14)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    if (typeof window !== "undefined") {
      window.sessionStorage.clear();
    }
  });

  it("IT-PASS-01: Não renderiza o card quando PublicKeyCredential não estiver disponível", () => {
    vi.stubGlobal("PublicKeyCredential", undefined);

    const { queryByTestId } = renderWithProviders(<PasskeyInvitationCard />);
    expect(queryByTestId("passkey-invitation-card")).not.toBeInTheDocument();
  });

  it("IT-PASS-02: Renderiza o card quando houver suporte a PublicKeyCredential e não estiver dispensado", () => {
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    const { getByTestId, getByText } = renderWithProviders(<PasskeyInvitationCard />);

    expect(getByTestId("passkey-invitation-card")).toBeInTheDocument();
    expect(getByText(/acesso rápido com biometria/i)).toBeInTheDocument();
    expect(getByText(/ativar biometria deste aparelho/i)).toBeInTheDocument();
  });

  it("IT-PASS-03: Clicar em 'Agora não' oculta o card e persiste no sessionStorage", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    const { getByRole, queryByTestId } = renderWithProviders(<PasskeyInvitationCard />);

    const btnAgoraNao = getByRole("button", { name: /agora não/i });
    await user.click(btnAgoraNao);

    expect(queryByTestId("passkey-invitation-card")).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem("medisync_passkey_invite_dismissed")).toBe("true");
  });

  it("IT-PASS-04: Clicar em 'Ativar Biometria deste Aparelho' aciona callback quando fornecido", async () => {
    const user = userEvent.setup();
    const handleAtivar = vi.fn();
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    const { getByRole } = renderWithProviders(
      <PasskeyInvitationCard onAtivarBiometria={handleAtivar} />,
    );

    const btnAtivar = getByRole("button", { name: /ativar biometria deste aparelho/i });
    await user.click(btnAtivar);

    expect(handleAtivar).toHaveBeenCalledTimes(1);
  });

  it("IT-PASS-05: Clicar em ativar sem callback exibe orientações honestas de suporte FIDO2 (US-14)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    const { getByRole, getByText } = renderWithProviders(<PasskeyInvitationCard />);

    const btnAtivar = getByRole("button", { name: /ativar biometria deste aparelho/i });
    await user.click(btnAtivar);

    expect(getByText(/suporte fido2 \/ passkeys detectado/i)).toBeInTheDocument();
    expect(getByText(/issue #115/i)).toBeInTheDocument();
  });
});
