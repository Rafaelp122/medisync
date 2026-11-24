import { AlertCircle, KeyRound, Loader2, Stethoscope } from "lucide-react";
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
import { settings } from "@/config/settings";
import type { StoredDoctorSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { useCorporateLogin } from "../api/use-corporate-login";
import { doctorLoginSchema } from "../schemas/auth-schemas";
import { MfaSetupModal } from "./mfa-setup-modal";
import { MfaVerifyModal } from "./mfa-verify-modal";

export interface DoctorLoginFormProps {
  onLoginSuccess: (session: StoredDoctorSession) => void;
  className?: string;
}

export function DoctorLoginForm({ onLoginSuccess, className }: DoctorLoginFormProps) {
  const [crm, setCrm] = useState(settings.env.isDemoMode ? "123456" : "");
  const [uf, setUf] = useState("SP");
  const [senha, setSenha] = useState(settings.env.isDemoMode ? settings.demo.doctorPassword : "");
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

      if (me.papel !== "MEDICO" || !me.ativo) {
        sessionTransport.clearSession("staff");
        setErro(
          "Acesso restrito a médicos plantonistas ativos (perfil MEDICO). Verifique suas credenciais.",
        );
        return;
      }

      const crmUf = `${crm.trim()}/${uf.trim().toUpperCase()}`;
      const session: StoredDoctorSession = {
        medicoId: me.usuario_id,
        medicoNome: me.identificador || crmUf,
        crmUf,
        identificador: me.identificador,
        papel: "MEDICO",
      };
      sessionTransport.activateStaffSession({ role: "MEDICO", token, session });
      onLoginSuccess(session);
    } catch (err) {
      sessionTransport.clearSession("staff");
      setErro(
        extractProblemDetail(
          err,
          "Não foi possível carregar o perfil do médico autenticado. Tente novamente.",
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
          "Credenciais médicas inválidas ou registro CRM não habilitado para telemedicina.",
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

    const result = doctorLoginSchema.safeParse({
      crm: crm.trim(),
      uf: uf.trim().toUpperCase(),
      senha,
    });

    if (!result.success) {
      setErro(result.error.issues[0]?.message ?? "Dados de CRM inválidos.");
      return;
    }

    const identificador =
      settings.env.isDemoMode && result.data.crm === "123456" && result.data.uf === "SP"
        ? settings.demo.doctorEmail
        : `${result.data.crm}/${result.data.uf}`;

    loginCorporate({
      identificador,
      senha: result.data.senha,
    });
  };

  const handlePreencherDemo = () => {
    setCrm("123456");
    setUf("SP");
    setSenha(settings.demo.doctorPassword);
    setErro(null);
    loginCorporate({
      identificador: settings.demo.doctorEmail,
      senha: settings.demo.doctorPassword,
    });
  };

  const isBusy = isPending || isHydratingProfile;

  return (
    <>
      <Card className={className}>
        <CardHeader className="space-y-2 text-center pb-4">
          <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <Stethoscope className="size-6" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-xl font-bold tracking-tight text-foreground">
              Acesso à Estação Médica
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground">
              Acesso restrito a médicos credenciados com CRM ativo e MFA TOTP (Resoluções CFM nº
              2.299/2021 e nº 2.314/2022).
            </CardDescription>
          </div>
          <div className="flex justify-center pt-1">
            <Badge variant="outline" className="text-[11px] py-0 px-2 gap-1 text-muted-foreground">
              <span>Plantão Digital • MediSync Express</span>
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
            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="medico-crm" className="text-xs font-semibold">
                  CRM: <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="medico-crm"
                  type="text"
                  placeholder="ex: 123456"
                  value={crm}
                  onChange={(e) => setCrm(e.target.value)}
                  disabled={isBusy}
                  className="text-xs h-9"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="medico-uf" className="text-xs font-semibold">
                  UF: <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="medico-uf"
                  type="text"
                  maxLength={2}
                  placeholder="SP"
                  value={uf}
                  onChange={(e) => setUf(e.target.value.toUpperCase())}
                  disabled={isBusy}
                  className="text-xs h-9 text-center uppercase"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="medico-senha" className="text-xs font-semibold">
                Senha de Acesso: <span className="text-destructive">*</span>
              </Label>
              <Input
                id="medico-senha"
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
                  <span>Autenticando plantonista…</span>
                </>
              ) : (
                <>
                  <KeyRound className="size-4" aria-hidden="true" />
                  <span>Entrar no Plantão</span>
                </>
              )}
            </Button>
          </form>

          {settings.env.isDemoMode && (
            <div className="pt-2 border-t border-border/60 text-center">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handlePreencherDemo}
                disabled={isBusy}
                className="text-xs h-8 text-muted-foreground hover:text-foreground"
              >
                Preencher credenciais de demonstração
              </Button>
            </div>
          )}
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
          perfilNome="Médico Plantonista"
          onSuccess={handleMfaSuccess}
        />
      )}
    </>
  );
}

export default DoctorLoginForm;
