import { AlertCircle, CheckCircle2, Loader2, UserPlus } from "lucide-react";
import { useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import type { RegistrarPacienteResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { StoredPatientSession } from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import {
  formatarTelefoneE164,
  limparDigitos,
  mascararCPF,
  mascararTelefoneBR,
} from "@/lib/validators";
import { usePatientSolicitarOtp } from "../api/use-patient-methods";
import { usePatientRegister } from "../api/use-patient-register";
import { patientRegisterSchema } from "../schemas/patient-hybrid-auth-schemas";
import { PatientOtpVerifyStep } from "./patient-otp-verify-step";

export interface PatientRegisterFormProps {
  onAuthenticated: (session: StoredPatientSession) => void;
  onGoToLogin?: () => void;
  className?: string;
}

/**
 * Formulário de auto-cadastro do cidadão (/cadastro) com aceite LGPD e confirmação OTP.
 * Regras canônicas: RF-01, LGPD Art. 11 e ADR-005.
 */
export function PatientRegisterForm({
  onAuthenticated,
  onGoToLogin,
  className,
}: PatientRegisterFormProps) {
  const [cpf, setCpf] = useState("");
  const [nomeCompleto, setNomeCompleto] = useState("");
  const [dataNascimento, setDataNascimento] = useState("");
  const [telefone, setTelefone] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [aceitePrivacidade, setAceitePrivacidade] = useState(false);

  const [registroResult, setRegistroResult] = useState<RegistrarPacienteResponse | null>(null);
  const [codigoDebug, setCodigoDebug] = useState<string | null>(null);
  const [telefoneE164, setTelefoneE164] = useState("");
  const [erroValidacao, setErroValidacao] = useState<string | null>(null);

  const registerMutation = usePatientRegister({
    onSuccess: (res) => {
      setCodigoDebug(res.codigo_debug ?? null);
      setRegistroResult(res);
    },
  });
  const solicitarOtp = usePatientSolicitarOtp({
    onSuccess: (res) => {
      setCodigoDebug(res.codigo_debug ?? null);
    },
  });

  const handleRegisterSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErroValidacao(null);

    const parsed = patientRegisterSchema.safeParse({
      cpf,
      nome_completo: nomeCompleto,
      data_nascimento: dataNascimento,
      telefone,
      email: email.trim().toLowerCase(),
      senha: senha.trim() ? senha : null,
      aceite_privacidade: aceitePrivacidade,
    });

    if (!parsed.success) {
      setErroValidacao(parsed.error.issues[0]?.message ?? "Verifique os dados informados.");
      return;
    }

    const e164 = formatarTelefoneE164(parsed.data.telefone);
    setTelefoneE164(e164);

    registerMutation.mutate({
      cpf: limparDigitos(parsed.data.cpf),
      nome_completo: parsed.data.nome_completo,
      data_nascimento: parsed.data.data_nascimento,
      telefone: e164,
      aceite_privacidade: true,
      email: parsed.data.email.trim().toLowerCase(),
      senha: parsed.data.senha ?? null,
    });
  };

  const erroAtivo =
    erroValidacao ??
    (registerMutation.isError
      ? extractProblemDetail(registerMutation.error)
      : solicitarOtp.isError
        ? extractProblemDetail(solicitarOtp.error)
        : null);

  return (
    <Card className={cn("w-full max-w-md mx-auto shadow-lg border", className)}>
      <CardHeader className="space-y-1.5 text-center pb-4">
        <div className="mx-auto size-11 rounded-full bg-primary/10 flex items-center justify-center text-primary">
          <UserPlus className="size-5" aria-hidden="true" />
        </div>
        <CardTitle className="text-xl font-bold tracking-tight text-foreground">
          {registroResult ? "Confirme seu celular" : "Cadastro do Cidadão"}
        </CardTitle>
        <CardDescription className="text-xs text-muted-foreground">
          {registroResult
            ? `Enviamos um código de 6 dígitos por SMS para ${registroResult.telefone_mascarado}.`
            : "Crie sua conta gratuita para atendimento rápido e acompanhamento da fila SUS."}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {erroAtivo && (
          <Alert variant="destructive" className="py-2.5 text-xs">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertDescription className="text-xs">{erroAtivo}</AlertDescription>
          </Alert>
        )}

        {registroResult ? (
          <div className="space-y-4">
            <Alert className="bg-acr-green/10 border-acr-green/30 text-foreground">
              <CheckCircle2 className="size-4 text-acr-green" aria-hidden="true" />
              <AlertTitle className="text-xs font-semibold">Cadastro realizado!</AlertTitle>
              <AlertDescription className="text-xs text-muted-foreground">
                Digite o código SMS de 6 dígitos para concluir seu primeiro acesso.
              </AlertDescription>
            </Alert>
            <PatientOtpVerifyStep
              inputId="register-otp-codigo"
              label="Código SMS (6 dígitos)"
              telefoneE164={telefoneE164}
              codigoDebug={codigoDebug}
              submitLabel="Confirmar e acessar"
              secondaryActionLabel={
                solicitarOtp.isPending ? "Reenviando código…" : "Reenviar código SMS"
              }
              secondaryActionPending={solicitarOtp.isPending}
              onSecondaryAction={() =>
                solicitarOtp.mutate({ telefone: telefoneE164, cpf: limparDigitos(cpf) })
              }
              onAuthenticated={onAuthenticated}
            />
          </div>
        ) : (
          <form onSubmit={handleRegisterSubmit} className="space-y-3.5" noValidate>
            <div className="space-y-1">
              <Label htmlFor="register-cpf" className="text-xs font-semibold">
                CPF <span className="text-destructive">*</span>
              </Label>
              <Input
                id="register-cpf"
                type="text"
                inputMode="numeric"
                placeholder="000.000.000-00"
                value={cpf}
                onChange={(e) => setCpf(mascararCPF(e.target.value))}
                disabled={registerMutation.isPending}
                className="min-h-[44px]"
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="register-nome" className="text-xs font-semibold">
                Nome Completo <span className="text-destructive">*</span>
              </Label>
              <Input
                id="register-nome"
                type="text"
                autoComplete="name"
                placeholder="Ex: Maria da Silva"
                value={nomeCompleto}
                onChange={(e) => setNomeCompleto(e.target.value)}
                disabled={registerMutation.isPending}
                className="min-h-[44px]"
                required
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="register-nascimento" className="text-xs font-semibold">
                  Data de Nascimento <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="register-nascimento"
                  type="date"
                  value={dataNascimento}
                  onChange={(e) => setDataNascimento(e.target.value)}
                  disabled={registerMutation.isPending}
                  className="min-h-[44px]"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="register-telefone" className="text-xs font-semibold">
                  Telefone Celular <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="register-telefone"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel-national"
                  placeholder="(11) 98765-4321"
                  value={telefone}
                  onChange={(e) => setTelefone(mascararTelefoneBR(e.target.value))}
                  disabled={registerMutation.isPending}
                  className="min-h-[44px]"
                  required
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="register-email" className="text-xs font-semibold">
                E-mail *
              </Label>
              <Input
                id="register-email"
                type="email"
                autoComplete="email"
                placeholder="voce@exemplo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={registerMutation.isPending}
                required
                className="min-h-[44px]"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="register-senha" className="text-xs font-semibold">
                Senha alternativa (opcional, mín. 8 caracteres)
              </Label>
              <Input
                id="register-senha"
                type="password"
                autoComplete="new-password"
                placeholder="Opcional para acesso sem celular"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                disabled={registerMutation.isPending}
                className="min-h-[44px]"
              />
            </div>
            <label
              htmlFor="register-lgpd"
              className="flex items-start gap-2.5 min-h-[44px] py-1.5 text-xs text-muted-foreground cursor-pointer select-none"
            >
              <input
                id="register-lgpd"
                type="checkbox"
                checked={aceitePrivacidade}
                onChange={(e) => setAceitePrivacidade(e.target.checked)}
                disabled={registerMutation.isPending}
                className="mt-0.5 size-4 shrink-0 rounded border-input accent-primary"
              />
              <span>
                Li e aceito a Política de Privacidade e o tratamento dos meus dados de saúde (LGPD).
              </span>
            </label>
            <Button
              type="submit"
              disabled={registerMutation.isPending}
              className="w-full min-h-[44px] text-sm font-semibold gap-2"
            >
              {registerMutation.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  <span>Criando cadastro…</span>
                </>
              ) : (
                <span>Criar conta e receber código SMS</span>
              )}
            </Button>
            {onGoToLogin && (
              <Button
                type="button"
                variant="ghost"
                onClick={onGoToLogin}
                className="w-full min-h-[44px] text-xs"
              >
                Já possui conta? Entrar
              </Button>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export default PatientRegisterForm;
