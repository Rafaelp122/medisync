import { AlertCircle, Building2, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { TokenResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setAccessToken } from "@/lib/auth-token";
import type { StoredManagerSession } from "@/lib/session-storage";
import { useCorporateLogin } from "../api/use-corporate-login";
import { managerLoginSchema } from "../schemas/auth-schemas";
import { MfaVerifyModal } from "./mfa-verify-modal";

export interface ManagerLoginFormProps {
  onLoginSuccess: (session: StoredManagerSession) => void;
  className?: string;
}

export function ManagerLoginForm({ onLoginSuccess, className }: ManagerLoginFormProps) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
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
          "E-mail institucional ou senha incorretos. Apenas gestores com perfil REGULACAO/GESTOR podem acessar.",
      );
    },
  });

  const finalizarLogin = (token: string) => {
    setAccessToken(token);
    const session: StoredManagerSession = {
      usuarioId: "018f3a5b-9999-4444-8888-018f3a5b9999",
      nome: "Gestor da Regulação Municipal",
      email: email.trim().toLowerCase(),
      papel: "GESTOR",
    };
    onLoginSuccess(session);
  };

  const handleMfaSuccess = (data: TokenResponse) => {
    finalizarLogin(data.access_token);
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

  return (
    <>
      <Card className={className}>
        <CardHeader className="space-y-2 text-center pb-4">
          <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <Building2 className="size-6" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-xl font-bold tracking-tight text-foreground">
              Acesso à Regulação Municipal
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground">
              Painel de telemetria, controle de cota e gestão da fila SUS em tempo real (RF-10 /
              US-13).
            </CardDescription>
          </div>
          <div className="flex justify-center pt-1">
            <Badge variant="outline" className="text-[11px] py-0 px-2 gap-1 text-muted-foreground">
              <ShieldCheck className="size-3 text-emerald-600" />
              <span>Acesso Corporativo Seguro • MFA TOTP</span>
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
            <div className="space-y-1.5">
              <Label htmlFor="gestor-email" className="text-xs font-semibold">
                E-mail Institucional: <span className="text-destructive">*</span>
              </Label>
              <Input
                id="gestor-email"
                type="email"
                autoComplete="username"
                placeholder="ex: regulacao@saude.gov.br"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isPending}
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
                  <span>Autenticando gestor…</span>
                </>
              ) : (
                <>
                  <KeyRound className="size-4" />
                  <span>Acessar Painel da Regulação</span>
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {tempToken && (
        <MfaVerifyModal
          open={mfaModalAberto}
          onOpenChange={setMfaModalAberto}
          tempToken={tempToken}
          perfilNome="Gestor Municipal"
          onSuccess={handleMfaSuccess}
        />
      )}
    </>
  );
}

export default ManagerLoginForm;
