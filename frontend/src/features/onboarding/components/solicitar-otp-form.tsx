import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { extractProblemDetail } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { mascararTelefoneBR } from "@/lib/validators";
import { useSolicitarOtp } from "../api/use-solicitar-otp";
import { type SolicitarOtpFormData, solicitarOtpSchema } from "../schemas/onboarding-schema";

export interface SolicitarOtpFormProps {
  onOtpSent?: (data: {
    telefone: string;
    expiraEmSegundos: number;
    codigoDebug?: string | null;
  }) => void;
  className?: string;
}

/**
 * Formulário de solicitação de código OTP de paciente com máscara telefônica BR e cooldown.
 * Regras canônicas: RF-01, US-02 (§5.1) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export function SolicitarOtpForm({ onOtpSent, className }: SolicitarOtpFormProps) {
  const [cooldown, setCooldown] = React.useState(0);
  const solicitarOtp = useSolicitarOtp();

  const form = useForm<SolicitarOtpFormData>({
    resolver: zodResolver(solicitarOtpSchema),
    defaultValues: {
      telefone: "",
      cpf: null,
    },
  });

  React.useEffect(() => {
    if (cooldown <= 0) return;
    const interval = setInterval(() => {
      setCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [cooldown]);

  const onSubmit = async (values: SolicitarOtpFormData) => {
    try {
      const response = await solicitarOtp.mutateAsync({
        telefone: values.telefone,
        cpf: values.cpf,
      });
      setCooldown(60);
      onOtpSent?.({
        telefone: values.telefone,
        expiraEmSegundos: response?.expira_em_segundos ?? 300,
        codigoDebug: response?.codigo_debug,
      });
    } catch {
      // Error handled by react-query error state
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className={`space-y-4 ${className ?? ""}`}>
        {solicitarOtp.isError && (
          <Alert variant="destructive">
            <AlertTitle>Não foi possível enviar o código</AlertTitle>
            <AlertDescription>{extractProblemDetail(solicitarOtp.error)}</AlertDescription>
          </Alert>
        )}

        <FormField
          control={form.control}
          name="telefone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Telefone Celular</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="tel"
                  inputMode="tel"
                  spellCheck={false}
                  placeholder="(11) 98765-4321…"
                  autoComplete="tel-national"
                  disabled={cooldown > 0 || solicitarOtp.isPending}
                  onChange={(e) => {
                    const masked = mascararTelefoneBR(e.target.value);
                    field.onChange(masked);
                  }}
                />
              </FormControl>
              <FormDescription>
                Informe o telefone cadastrado no seu atendimento para receber o código SMS de
                acesso.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="p-3 bg-muted/60 rounded-md text-xs text-muted-foreground border">
          <p>
            <strong>Primeiro atendimento no MediSync?</strong> Inicie pelo 'Novo Atendimento' para
            realizar sua triagem clínica.
          </p>
        </div>

        <Button
          type="submit"
          className="w-full"
          disabled={cooldown > 0 || solicitarOtp.isPending}
          aria-busy={solicitarOtp.isPending}
        >
          {solicitarOtp.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
              Enviando código…
            </>
          ) : cooldown > 0 ? (
            `Reenviar código em ${cooldown}s…`
          ) : (
            "Receber código"
          )}
        </Button>
      </form>
    </Form>
  );
}
