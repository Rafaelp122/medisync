import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProblemDetailsError } from "@/api/errors";
import {
  handlePostAuthPatientWebauthnRegisterOptions,
  handlePostAuthPatientWebauthnRegisterVerify,
} from "@/api/generated/msw.gen";
import { registerPatientPasskeyCredential } from "@/lib/webauthn";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PasskeyInvitationCard } from "../components/passkey-invitation-card";

const originalCredentialsDescriptor =
  typeof navigator !== "undefined"
    ? Object.getOwnPropertyDescriptor(navigator, "credentials")
    : undefined;

describe("PasskeyInvitationCard (Convite Não-Bloqueante de Biometria - US-14)", () => {
  afterEach(() => {
    if (typeof navigator !== "undefined") {
      if (originalCredentialsDescriptor) {
        Object.defineProperty(navigator, "credentials", originalCredentialsDescriptor);
      } else {
        Reflect.deleteProperty(navigator, "credentials");
      }
    }
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

  it("IT-PASS-05: Clicar em ativar sem token ou credencial WebAuthn exibe alerta de indisponibilidade sem placeholder Issue #115", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    const { getByRole, queryByText } = renderWithProviders(<PasskeyInvitationCard />);

    const btnAtivar = getByRole("button", { name: /ativar biometria deste aparelho/i });
    await user.click(btnAtivar);

    expect(getByRole("alert")).toHaveTextContent(
      /sessão ou suporte biométrico indisponível neste navegador/i,
    );
    expect(queryByText(/issue #115/i)).not.toBeInTheDocument();
  });

  it("IT-PASS-06: Clicar em ativar com token executa cerimônia WebAuthn completa e envia publicKey SPKI", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});

    let capturedPublicKey: unknown;
    server.use(
      handlePostAuthPatientWebauthnRegisterOptions({
        body: {
          challenge: "Y2hhbGxlbmdlLTEyMw",
          rp: { name: "MediSync PA Virtual", id: "localhost" },
          user: {
            id: "cGFjaWVudGUtMTIz",
            name: "Paciente Teste",
            displayName: "Paciente Teste",
          },
          pubKeyCredParams: [{ type: "public-key", alg: -7 }],
          timeout: 60000,
          attestation: "none",
          authenticatorSelection: {
            residentKey: "required",
            requireResidentKey: true,
            userVerification: "preferred",
          },
        },
      }),
      handlePostAuthPatientWebauthnRegisterVerify(async ({ request }) => {
        const body = await request.json();
        capturedPublicKey = body.response.publicKey;
        return HttpResponse.json({
          status: "registrado",
          credencial_id: body.id,
        });
      }),
    );

    const createSpy = vi.fn().mockResolvedValue({
      id: "cred-webauthn-01",
      rawId: new Uint8Array([1, 2, 3, 4]).buffer,
      type: "public-key",
      response: {
        clientDataJSON: new Uint8Array([10, 20, 30]).buffer,
        attestationObject: new Uint8Array([40, 50, 60]).buffer,
        getPublicKey: () => new Uint8Array([70, 80, 90]).buffer,
      },
    });
    Object.defineProperty(navigator, "credentials", {
      value: { create: createSpy },
      configurable: true,
    });

    const { getByRole, findByRole } = renderWithProviders(
      <PasskeyInvitationCard
        token="intake-token.assinatura"
        onRegisterPasskey={registerPatientPasskeyCredential}
      />,
    );

    const btnAtivar = getByRole("button", { name: /ativar biometria deste aparelho/i });
    await user.click(btnAtivar);

    const statusMsg = await findByRole("status");
    expect(statusMsg).toHaveTextContent(/biometria ativada com sucesso neste aparelho/i);
    expect(createSpy).toHaveBeenCalledTimes(1);
    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        publicKey: expect.objectContaining({
          authenticatorSelection: expect.objectContaining({
            residentKey: "required",
            requireResidentKey: true,
          }),
        }),
      }),
    );
    expect(capturedPublicKey).toBeTruthy();
  });

  it("IT-PASS-07: Falha em onRegisterPasskey exibe alerta acessível sem vazar unhandled rejection", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("PublicKeyCredential", class FakePublicKeyCredential {});
    Object.defineProperty(navigator, "credentials", {
      value: { create: vi.fn() },
      configurable: true,
    });

    const failingRegister = vi.fn().mockRejectedValue(
      new ProblemDetailsError({
        status: 400,
        title: "Bad Request",
        detail: "Dispositivo não suportou atestação biométrica.",
      }),
    );

    const { getByRole, findByRole } = renderWithProviders(
      <PasskeyInvitationCard token="intake-token.assinatura" onRegisterPasskey={failingRegister} />,
    );

    await user.click(getByRole("button", { name: /ativar biometria deste aparelho/i }));

    expect(await findByRole("alert")).toHaveTextContent(
      /dispositivo não suportou atestação biométrica/i,
    );
    expect(failingRegister).toHaveBeenCalledWith({ token: "intake-token.assinatura" });
  });
});
