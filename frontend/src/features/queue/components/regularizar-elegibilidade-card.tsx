import { AlertCircle, CheckCircle2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useRegularizarFila } from "../api/use-regularizar-fila";

export interface RegularizarElegibilidadeCardProps {
  atendimentoId: string;
  token?: string;
}

/**
 * Cartão de ação direta para regularizar atendimento retido por elegibilidade (US-05 / RN03).
 */
export function RegularizarElegibilidadeCard({
  atendimentoId,
  token,
}: RegularizarElegibilidadeCardProps) {
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);
  const { mutate: regularizar, isPending, error } = useRegularizarFila();

  const handleRegularizar = () => {
    setMensagemSucesso(null);
    regularizar(
      { atendimentoId, token },
      {
        onSuccess: (res) => {
          setMensagemSucesso(
            res.mensagem || "Elegibilidade regularizada com sucesso na fila virtual.",
          );
        },
      },
    );
  };

  return (
    <Card
      role="region"
      aria-label="Regularização de elegibilidade cadastral"
      className="border-amber-400 bg-amber-50/80 shadow-sm dark:border-amber-700 dark:bg-amber-950/25"
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base text-amber-950 dark:text-amber-100">
          <ShieldCheck className="h-5 w-5 text-amber-700 dark:text-amber-400" aria-hidden="true" />
          Regularização de Elegibilidade Pendente
        </CardTitle>
        <CardDescription className="text-amber-900 dark:text-amber-200">
          Seu atendimento está retido aguardando confirmação de elegibilidade SUS. Regularize agora
          para ingressar na fila ativa de teleatendimento.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Falha ao regularizar elegibilidade</AlertTitle>
            <AlertDescription>
              {error.detail || error.message || "Não foi possível regularizar o atendimento."}
            </AlertDescription>
          </Alert>
        )}

        {mensagemSucesso && (
          <Alert
            role="status"
            className="border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
          >
            <CheckCircle2
              className="h-4 w-4 text-emerald-700 dark:text-emerald-400"
              aria-hidden="true"
            />
            <AlertTitle>Atendimento regularizado</AlertTitle>
            <AlertDescription>{mensagemSucesso}</AlertDescription>
          </Alert>
        )}

        <Button
          type="button"
          onClick={handleRegularizar}
          disabled={isPending}
          className="w-full sm:w-auto bg-amber-700 text-white hover:bg-amber-800"
        >
          {isPending ? "Regularizando…" : "Regularizar Elegibilidade Agora"}
        </Button>
      </CardContent>
    </Card>
  );
}
