import { AlertCircle, ArrowLeft, ArrowRight, Loader2, ShieldCheck, UserPlus } from "lucide-react";
import { useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import type { IdentificarPacienteResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mascararCPF } from "@/lib/validators";
import { usePatientIdentify } from "../api/use-patient-identify";
import {
  normalizarIdentificadorCidadao,
  patientIdentifySchema,
} from "../schemas/patient-hybrid-auth-schemas";

export interface PatientIdentifyFormProps {
  onIdentified: (payload: { identificador: string; response: IdentificarPacienteResponse }) => void;
  govbrHabilitado?: boolean;
  onGovbrLogin?: () => void;
  className?: string;
}

/**
 * Passo 1 do IAM Híbrido do Cidadão: identificação única por CPF ou e-mail.
 * Aplica máscara de CPF dinamicamente apenas quando a entrada é numérica.
 */
export function PatientIdentifyForm({
  onIdentified,
  govbrHabilitado = false,
  onGovbrLogin,
  className,
}: PatientIdentifyFormProps) {
  const [identificador, setIdentificador] = useState("");
  const [erroValidacao, setErroValidacao] = useState<string | null>(null);

  const identifyMutation = usePatientIdentify({
    onSuccess: (response) => {
      onIdentified({
        identificador: normalizarIdentificadorCidadao(identificador),
        response,
      });
    },
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErroValidacao(null);
    const raw = e.target.value;
    setIdentificador(/^[0-9.-]+$/.test(raw) ? mascararCPF(raw) : raw);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErroValidacao(null);
    const validation = patientIdentifySchema.safeParse({ identificador });
    if (!validation.success) {
      setErroValidacao(
        validation.error.issues[0]?.message ?? "Informe um CPF válido ou e-mail cadastrado.",
      );
      return;
    }
    identifyMutation.mutate({
      identificador: normalizarIdentificadorCidadao(validation.data.identificador),
    });
  };

  const erroMensagem =
    erroValidacao ??
    (identifyMutation.isError ? extractProblemDetail(identifyMutation.error) : null);

  return (
    <form onSubmit={handleSubmit} className={className ?? "space-y-4"} noValidate>
      {erroMensagem && (
        <Alert variant="destructive" className="py-2.5 text-xs">
          <AlertCircle className="size-4" aria-hidden="true" />
          <AlertDescription className="text-xs">{erroMensagem}</AlertDescription>
        </Alert>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="patient-identificador" className="text-sm font-semibold">
          CPF ou E-mail <span className="text-destructive">*</span>
        </Label>
        <Input
          id="patient-identificador"
          type="text"
          autoComplete="username"
          spellCheck={false}
          placeholder="000.000.000-00 ou voce@exemplo.com"
          value={identificador}
          onChange={handleChange}
          disabled={identifyMutation.isPending}
          className="min-h-[44px] text-sm"
          required
        />
        <p className="text-xs text-muted-foreground">
          Digite seu CPF ou e-mail para identificarmos suas opções de acesso seguro.
        </p>
      </div>
      <Button
        type="submit"
        disabled={identifyMutation.isPending}
        aria-busy={identifyMutation.isPending}
        className="w-full min-h-[44px] text-sm font-semibold gap-2"
      >
        {identifyMutation.isPending ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span>Identificando…</span>
          </>
        ) : (
          <>
            <span>Continuar</span>
            <ArrowRight className="size-4" aria-hidden="true" />
          </>
        )}
      </Button>
      {govbrHabilitado && onGovbrLogin && (
        <div className="pt-2 border-t border-border/60">
          <Button
            type="button"
            variant="outline"
            onClick={onGovbrLogin}
            disabled={identifyMutation.isPending}
            className="w-full min-h-[44px] text-sm font-semibold gap-2"
          >
            <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
            <span>Entrar com Gov.br</span>
          </Button>
        </div>
      )}
    </form>
  );
}

/**
 * Painel empático exibido quando o identificador informado ainda não possui conta.
 */
export function PatientNotFoundPanel({
  identificador,
  onGoToRegister,
  onRetry,
}: {
  identificador: string;
  onGoToRegister?: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-4">
      <Alert className="bg-muted/50">
        <UserPlus className="size-4 text-primary" aria-hidden="true" />
        <AlertTitle className="text-sm font-semibold">Primeiro acesso no MediSync?</AlertTitle>
        <AlertDescription className="text-xs text-muted-foreground">
          Não encontramos uma conta vinculada a <strong>{identificador}</strong>. Crie seu cadastro
          rápido em menos de 1 minuto para iniciar seu atendimento.
        </AlertDescription>
      </Alert>
      {onGoToRegister ? (
        <Button type="button" onClick={onGoToRegister} className="w-full min-h-[44px] gap-2">
          <UserPlus className="size-4" aria-hidden="true" />
          <span>Criar minha conta</span>
        </Button>
      ) : (
        <Button asChild className="w-full min-h-[44px] gap-2">
          <a href="/cadastro">
            <UserPlus className="size-4" aria-hidden="true" />
            <span>Criar minha conta</span>
          </a>
        </Button>
      )}
      <Button
        type="button"
        variant="ghost"
        onClick={onRetry}
        className="w-full min-h-[44px] text-xs"
      >
        <ArrowLeft className="size-4 mr-1.5" aria-hidden="true" />
        Tentar outro CPF ou e-mail
      </Button>
    </div>
  );
}

export default PatientIdentifyForm;
