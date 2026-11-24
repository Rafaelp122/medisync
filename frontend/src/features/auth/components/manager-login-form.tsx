import { AlertCircle, Building2, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { client } from "@/api/client";
import { extractProblemDetail } from "@/api/errors";
import { meApiV1AuthMeGet } from "@/api/generated/sdk.gen";
import type { TokenResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { StoredManagerSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { useCorporateLogin } from "../api/use-corporate-login";
import { managerLoginSchema } from "../schemas/auth-schemas";
import { MfaSetupModal } from "./mfa-setup-modal";
import { MfaVerifyModal } from "./mfa-verify-modal";

export interface ManagerLoginFormProps {
  onLoginSuccess: (session: StoredManagerSession) => void;
  className?: string;
}

export function ManagerLoginForm({ onLoginSuccess, className }: ManagerLoginFormProps) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [isHydratingProfile, setIsHydratingProfile] = useState(false);

  const [mfaSetupAberto, setMfaSetupAberto] = useState(false);
  const [mfaVerifyAberto, setMfaVerifyAberto] = useState(false);
  const [tempToken, setTempToken] = useState<string | null>(null);

  const finalizarLogin = async (token: string) => {
    setIsHydratingProfile(true);
    try {
      const meResponse = await meApiV1AuthMeGet({
        client,
        headers: { Authorization: `Bearer ${token}` },
        throwOnError: true,
      });
      const me = meResponse.data;

      if (me.papel !== "GESTOR_UNIDADE" || !me.ativo) {
        sessionTransport.clearSession("staff");
        setErro("Acesso restrito a gestores da unidade ativos (perfil GESTOR_UNIDADE).");
        return;
      }

      const normalizedEmail = email.trim().toLowerCase();
      const session: StoredManagerSession = {
        usuarioId: me.usuario_id,
        nome: me.identificador || normalizedEmail,
        email: normalizedEmail,
        papel: "GESTOR_UNIDADE",
      };
      sessionTransport.activateStaffSession({ role: "GESTOR_UNIDADE", token, session });
      onLoginSuccess(session);
    } catch (err) {
      sessionTransport.clearSession("staff");
      setErro(
        extractProblemDetail(
          err,
          "Não foi possível carregar o perfil do gestor autenticado. Tente novamente.",
        ),
      );
    } finally {
      setIsHydratingProfile(false);
    }
  };

  const { mutate: loginCorporate, isPending } = useCorporateLogin({
    onSuccess: (data: TokenResponse) => {
      if (data.mfa_setup_requerido) {
        setTempToken(data.access_token);
        setMfaSetupAberto(true);
        return;
      }
      if (data.mfa_requerido) {
        setTempToken(data.access_token);
        setMfaVerifyAberto(true);
        return;
      }
      void finalizarLogin(data.access_token);
    },
    onError: (err) => {
      setErro(
        err.detail ||
          err.message ||
          "E-mail institucional ou senha incorretos. Apenas gestores com perfil GESTOR_UNIDADE podem acessar.",
      );
    },
  });

  const handleMfaActivated = () => {
    setMfaSetupAberto(false);
    setMfaVerifyAberto(true);
  };

  const handleMfaSuccess = (data: TokenResponse) => {
    void finalizarLogin(data.access_token);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErro(null);

    const result = managerLoginSchema.safeParse({
      email: email.trim().toLowerCase(),
      senha,
    });

    if (!result.success) {
      setErro(result.error.issues[0]?.message ?? "Dados de acesso inválidos.");
      return;
    }

    loginCorporate({
      identificador: result.data.email,
      senha: result.data.senha,
    });
  };

  const isBusy = isPending || isHydratingProfile;

  return (
    <>
      <Card className={className}>
        <CardHeader className="space-y-2 text-center pb-4">
          <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <Building2 className="size-6" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-xl font-bold tracking-tight text-foreground">
              Acesso da Gestão da Unidade
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground">
              Painel de telemetria, controle de cota e gestão da fila SUS em tempo real (RF-10 /
              US-13).
            </CardDescription>
          </div>
          <div className="flex justify-center pt-1">
            <Badge variant="outline" className="text-[11px] py-0 px-2 gap-1 text-muted-foreground">
              <ShieldCheck className="size-3 text-acr-green" aria-hidden="true" />
              <span>Acesso Corporativo Seguro • MFA TOTP</span>
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {erro && (
            <Alert variant="destructive" className="py-2.5 text-xs">
              <AlertCircle className="size-4" aria-hidden="true" />
              <AlertDescription className="text-xs">{erro}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div className="space-y-1.5">
              <Label htmlFor="gestor-email" className="text-xs font-semibold">
                E-mail Institucional: <span className="text-destructive">*</span>
              </Label>
              <Input
                id="gestor-email"
                type="email"
                autoComplete="username"
                placeholder="ex: gestor@unidade.saude.gov.br"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isBusy}
                className="text-xs h-9"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="gestor-senha" className="text-xs font-semibold">
                Senha Institucional: <span className="text-destructive">*</span>
              </Label>
              <Input
                id="gestor-senha"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                disabled={isBusy}
                className="text-xs h-9"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={isBusy}
              className="w-full text-xs font-semibold h-10 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 mt-2"
            >
              {isBusy ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>Autenticando gestor…</span>
                </>
              ) : (
                <>
                  <KeyRound className="size-4" aria-hidden="true" />
                  <span>Acessar Painel da Unidade</span>
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {tempToken && (
        <MfaSetupModal
          open={mfaSetupAberto}
          onOpenChange={setMfaSetupAberto}
          tempToken={tempToken}
          onActivated={handleMfaActivated}
        />
      )}

      {tempToken && (
        <MfaVerifyModal
          open={mfaVerifyAberto}
          onOpenChange={setMfaVerifyAberto}
          tempToken={tempToken}
          perfilNome="Gestor da Unidade"
          onSuccess={handleMfaSuccess}
        />
      )}
    </>
  );
}

export default ManagerLoginForm;
