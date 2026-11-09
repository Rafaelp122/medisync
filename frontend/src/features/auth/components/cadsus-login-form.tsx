import { AlertCircle, ArrowRight, HeartPulse, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mascararCNS, mascararCPF } from "@/lib/validators";
import { useCadsusLogin } from "../api/use-cadsus-login";
import { cadsusAuthSchema } from "../schemas/auth-schemas";

export interface CadsusLoginFormProps {
  onSuccess: (data: VerificarOtpResponse) => void;
  onAlternarOtp?: () => void;
  className?: string;
}

export function CadsusLoginForm({ onSuccess, onAlternarOtp, className }: CadsusLoginFormProps) {
  const [cpf, setCpf] = useState("");
  const [cns, setCns] = useState("");
  const [dataNascimento, setDataNascimento] = useState("");
  const [nomeMae, setNomeMae] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const { mutate: loginCadsus, isPending } = useCadsusLogin({
    onSuccess: (data) => {
      onSuccess(data);
    },
    onError: (err) => {
      setErro(
        err.detail ||
          err.message ||
          "Registro não localizado no CADSUS / Base Nacional. Verifique os dados ou utilize o acesso por telefone.",
      );
    },
  });

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErro(null);

    const result = cadsusAuthSchema.safeParse({
      cpf,
      cns: cns.trim() || undefined,
      dataNascimento,
      nomeMae: nomeMae.trim(),
    });

    if (!result.success) {
      setErro(result.error.issues[0]?.message ?? "Dados civis incompletos ou inválidos.");
      return;
    }

    loginCadsus(result.data);
  };

  return (
    <Card className={className}>
      <CardHeader className="space-y-2 text-center pb-4">
        <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
          <HeartPulse className="size-6" />
        </div>
        <div className="space-y-1">
          <CardTitle className="text-xl font-bold tracking-tight text-foreground">
            Acesso Cidadão SUS (Gov.br / CADSUS)
          </CardTitle>
          <CardDescription className="text-xs text-muted-foreground">
            Autenticação sem senha via desambiguação de dados civis oficiais do Ministério da Saúde.
          </CardDescription>
        </div>
        <div className="flex justify-center pt-1">
          <Badge variant="outline" className="text-[11px] py-0 px-2 gap-1 text-muted-foreground">
            <ShieldCheck className="size-3 text-emerald-600" />
            <span>Validação Federal DATASUS • Lei Geral de Proteção de Dados</span>
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
            <Label htmlFor="cadsus-cpf" className="text-xs font-semibold">
              CPF do Paciente: <span className="text-destructive">*</span>
            </Label>
            <Input
              id="cadsus-cpf"
              type="text"
              inputMode="numeric"
              placeholder="000.000.000-00"
              value={cpf}
              onChange={(e) => setCpf(mascararCPF(e.target.value))}
              maxLength={14}
              disabled={isPending}
              className="text-xs h-9"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cadsus-cns" className="text-xs font-semibold">
              Cartão Nacional de Saúde (CNS - Opcional):
            </Label>
            <Input
              id="cadsus-cns"
              type="text"
              inputMode="numeric"
              placeholder="000 0000 0000 0000"
              value={cns}
              onChange={(e) => setCns(mascararCNS(e.target.value))}
              maxLength={18}
              disabled={isPending}
              className="text-xs h-9"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cadsus-nascimento" className="text-xs font-semibold">
              Data de Nascimento: <span className="text-destructive">*</span>
            </Label>
            <Input
              id="cadsus-nascimento"
              type="date"
              value={dataNascimento}
              onChange={(e) => setDataNascimento(e.target.value)}
              disabled={isPending}
              className="text-xs h-9"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cadsus-mae" className="text-xs font-semibold">
              Nome Completo da Mãe: <span className="text-destructive">*</span>
            </Label>
            <Input
              id="cadsus-mae"
              type="text"
              placeholder="Conforme certidão ou documento de identidade"
              value={nomeMae}
              onChange={(e) => setNomeMae(e.target.value)}
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
                <span>Localizando prontuário no CADSUS…</span>
              </>
            ) : (
              <>
                <span>Acessar Atendimento</span>
                <ArrowRight className="size-4" />
              </>
            )}
          </Button>
        </form>

        {onAlternarOtp && (
          <div className="pt-2 border-t border-border/60 text-center">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onAlternarOtp}
              className="text-xs h-8 text-muted-foreground hover:text-foreground"
            >
              Prefere entrar com código SMS no celular? Clique aqui
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default CadsusLoginForm;
