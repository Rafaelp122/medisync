import { AlertCircle, KeyRound, Loader2, Stethoscope } from "lucide-react";
import { useState } from "react";
import type { TokenResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { settings } from "@/config/settings";
import { setAccessToken } from "@/lib/auth-token";
import type { StoredDoctorSession } from "@/lib/session-storage";
import { useCorporateLogin } from "../api/use-corporate-login";
import { doctorLoginSchema } from "../schemas/auth-schemas";
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

  const [mfaModalAberto, setMfaModalAberto] = useState(false);
  const [tempToken, setTempToken] = useState<string | null>(null);

  const { mutate: loginCorporate, isPending } = useCorporateLogin({
    onSuccess: (data: TokenResponse) => {
      if (data.mfa_requerido) {
        setTempToken(data.access_token);
        setMfaModalAberto(true);
      } else {
        finalizarLogin(data.access_token);
      }
    },
    onError: (err) => {
      setErro(
        err.detail ||
          err.message ||
          "Credenciais médicas inválidas ou registro CRM não habilitado para telemedicina.",
      );
    },
  });

  const finalizarLogin = (token: string) => {
    setAccessToken(token);
    const session: StoredDoctorSession = {
      medicoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
      medicoNome: "Dr. Eduardo Rocha",
      crmUf: `${crm.trim()}/${uf.toUpperCase()}`,
      identificador: `${crm.trim()}/${uf.toUpperCase()}`,
    };
    onLoginSuccess(session);
  };

  const handleMfaSuccess = (data: TokenResponse) => {
    finalizarLogin(data.access_token);
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

  return (
    <>
      <Card className={className}>
        <CardHeader className="space-y-2 text-center pb-4">
          <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <Stethoscope className="size-6" />
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
              <AlertCircle className="size-4" />
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
                  disabled={isPending}
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
                  disabled={isPending}
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
                disabled={isPending}
                className="text-xs h-9"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={isPending}
              className="w-full text-xs font-semibold h-10 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 mt-2"
            >
              {isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>Autenticando plantonista…</span>
                </>
              ) : (
                <>
                  <KeyRound className="size-4" />
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
                disabled={isPending}
                className="text-xs h-8 text-muted-foreground hover:text-foreground"
              >
                Preencher credenciais demo (Dr. Eduardo Rocha)
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {tempToken && (
        <MfaVerifyModal
          open={mfaModalAberto}
          onOpenChange={setMfaModalAberto}
          tempToken={tempToken}
          perfilNome="Médico Plantonista"
          onSuccess={handleMfaSuccess}
        />
      )}
    </>
  );
}

export default DoctorLoginForm;
