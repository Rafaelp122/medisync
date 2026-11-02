import { AlertCircle, KeyRound, Loader2, Stethoscope } from "lucide-react";
import { useState } from "react";
import { client, getActiveTenantId } from "@/api/client";
import { toProblemDetailsError } from "@/api/errors";
import { loginApiV1AuthLoginPost } from "@/api/generated/sdk.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { settings } from "@/config/settings";
import type { StoredDoctorSession } from "@/lib/session-storage";

export interface DoctorLoginCardProps {
  onLoginSuccess: (session: StoredDoctorSession) => void;
}

/**
 * Card de Autenticação Corporativa do Médico Plantonista.
 * Conecta-se a POST /api/v1/auth/login emitindo Bearer JWT para a estação clínica.
 * Regras: docs/user-stories/US-09-teleconsulta-pep-soap.md, RF-01, RF-03 e CFM nº 2.314/2022.
 */
export function DoctorLoginCard({ onLoginSuccess }: DoctorLoginCardProps) {
  const [identificador, setIdentificador] = useState(
    settings.env.isDemoMode ? settings.demo.doctorEmail : "",
  );
  const [senha, setSenha] = useState(settings.env.isDemoMode ? settings.demo.doctorPassword : "");
  const [isLoading, setIsLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const handlePreencherDemo = () => {
    setIdentificador(settings.demo.doctorEmail);
    setSenha(settings.demo.doctorPassword);
    setErro(null);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErro(null);

    if (!identificador.trim() || !senha.trim()) {
      setErro("Informe o e-mail/identificador e a senha para entrar no plantão.");
      return;
    }

    setIsLoading(true);

    try {
      const response = await loginApiV1AuthLoginPost({
        client,
        headers: {
          "X-Tenant-ID": getActiveTenantId(),
        },
        body: {
          identificador: identificador.trim().toLowerCase(),
          senha,
          organizacao_id: Number.parseInt(getActiveTenantId(), 10) || 1,
        },
        throwOnError: true,
      });

      const session: StoredDoctorSession = {
        token: response.data.access_token,
        medicoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
        medicoNome: "Dr. Eduardo Rocha",
        crmUf: "123456/SP",
        identificador: identificador.trim().toLowerCase(),
      };

      onLoginSuccess(session);
    } catch (err) {
      const problem = toProblemDetailsError(err);
      setErro(
        problem.detail ||
          "Falha na autenticação médica. Verifique as credenciais ou o tenant ativo.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="w-full max-w-md mx-auto shadow-md border-border bg-card">
      <CardHeader className="space-y-2 text-center pb-4">
        <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
          <Stethoscope className="size-6" />
        </div>
        <div className="space-y-1">
          <CardTitle className="text-xl font-bold tracking-tight text-foreground">
            Acesso à Estação Médica
          </CardTitle>
          <CardDescription className="text-xs text-muted-foreground">
            Acesso exclusivo a médicos plantonistas credenciados (CFM nº 2.314/2022).
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
          <div className="space-y-1.5">
            <Label htmlFor="medico-identificador" className="text-xs font-semibold">
              E-mail Corporativo ou CRM:
            </Label>
            <Input
              id="medico-identificador"
              type="text"
              autoComplete="username"
              placeholder="ex: eduardo.rocha@medisync.com.br"
              value={identificador}
              onChange={(e) => setIdentificador(e.target.value)}
              className="text-xs h-9"
              disabled={isLoading}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="medico-senha" className="text-xs font-semibold">
              Senha:
            </Label>
            <Input
              id="medico-senha"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className="text-xs h-9"
              disabled={isLoading}
            />
          </div>

          <Button
            type="submit"
            disabled={isLoading}
            className="w-full text-xs font-semibold h-9 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {isLoading ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span>Autenticando plantonista…</span>
              </>
            ) : (
              <>
                <KeyRound className="size-3.5" />
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
              className="text-[11px] h-7 text-muted-foreground hover:text-foreground"
            >
              Preencher credenciais demo (Dr. Eduardo Rocha)
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
