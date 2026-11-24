import { useRef, useState } from "react";
import { SamuEmergencyModal } from "@/components/samu-emergency-modal";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Form } from "@/components/ui/form";
import { useWalkinAcolhimentoFlow } from "../hooks/use-walkin-acolhimento-flow";
import { SamuPresencialRedirectCard } from "./samu-presencial-redirect-card";
import { TcleDialog } from "./tcle-dialog";
import {
  SINAIS_ALARME_CRITICOS,
  SINTOMAS_COMUNS,
  TriageClinicalStep,
} from "./triage-clinical-step";
import { TriageIdentificationStep } from "./triage-identification-step";

export { SINAIS_ALARME_CRITICOS, SINTOMAS_COMUNS };

export interface AcolhimentoConcluidoData {
  pacienteId: string;
  atendimentoId: string;
  token: string;
  prioridadeClinica: number;
  isNovoPaciente: boolean;
}

export interface AcolhimentoFase1FormProps {
  onAdmissaoConcluida: (data: AcolhimentoConcluidoData) => void;
  onVoltarParaLogin?: () => void;
}

/**
 * Formulário de Acolhimento Rápido Walk-In (<170L via `useWalkinAcolhimentoFlow`).
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function AcolhimentoFase1Form({
  onAdmissaoConcluida,
  onVoltarParaLogin,
}: AcolhimentoFase1FormProps) {
  const [tcleDialogOpen, setTcleDialogOpen] = useState(false);
  const errorBannerRef = useRef<HTMLDivElement>(null);
  const flow = useWalkinAcolhimentoFlow(onAdmissaoConcluida);

  const scrollError = () => errorBannerRef.current?.scrollIntoView({ behavior: "smooth" });
  const tcleAceito = Boolean(flow.form.watch("aceite_tcle"));

  if (flow.encaminhadoPresencial) {
    return (
      <SamuPresencialRedirectCard orientacoes={flow.orientacoesSamu} onReiniciar={flow.reiniciar} />
    );
  }

  return (
    <>
      <Card className="w-full max-w-xl mx-auto shadow-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-primary">
              {flow.microEtapa === "identificacao"
                ? "Acolhimento Rápido • Etapa 1 de 2: Identificação"
                : "Acolhimento Rápido • Etapa 2 de 2: Triagem Clínica"}
            </span>
            {onVoltarParaLogin && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onVoltarParaLogin}
                className="text-xs h-7 px-2"
              >
                Já possui atendimento? Acesse com seu telefone
              </Button>
            )}
          </div>
          <CardTitle className="text-2xl font-bold">Pronto Atendimento Virtual</CardTitle>
          <CardDescription>
            {flow.microEtapa === "identificacao"
              ? "Preencha seus dados de identificação para triagem imediata."
              : "Conte-nos o que você está sentindo e informe a intensidade dos sintomas."}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {flow.erroHumanizado && (
            <Alert variant="destructive" className="mb-4" ref={errorBannerRef} role="alert">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <AlertTitle className="font-bold">{flow.erroHumanizado.title}</AlertTitle>
                  <AlertDescription className="mt-1 text-sm leading-relaxed">
                    {flow.erroHumanizado.detail}
                  </AlertDescription>
                </div>
                {flow.erroHumanizado.retryable && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={flow.form.handleSubmit((v) => flow.submeter(v, scrollError))}
                    disabled={flow.isSubmitting}
                    className="text-xs shrink-0 border-destructive/40 hover:bg-destructive/10"
                  >
                    🔄 Tentar Novamente
                  </Button>
                )}
              </div>
            </Alert>
          )}

          <Form {...flow.form}>
            <form
              onSubmit={flow.form.handleSubmit((v) => flow.submeter(v, scrollError))}
              className="space-y-4"
            >
              {flow.microEtapa === "identificacao" ? (
                <TriageIdentificationStep
                  control={flow.form.control}
                  tipoDoc={flow.tipoDoc}
                  isSubmitting={flow.isSubmitting}
                  onAlternarParaCpf={flow.alternarParaCpf}
                  onAlternarParaCns={flow.alternarParaCns}
                  onAvancar={() => void flow.avancarParaTriagem(scrollError)}
                />
              ) : (
                <TriageClinicalStep
                  control={flow.form.control}
                  sintomasSelecionados={flow.sintomasSelecionados}
                  escalaDor={flow.escalaDor}
                  tcleAceito={tcleAceito}
                  isSubmitting={flow.isSubmitting}
                  onToggleSintoma={flow.toggleSintoma}
                  onEscalaDorChange={flow.setEscalaDor}
                  onTcleChange={(checked) =>
                    flow.form.setValue("aceite_tcle", checked, { shouldValidate: true })
                  }
                  onAbrirTcle={() => setTcleDialogOpen(true)}
                  onVoltar={() => {
                    flow.limparErro();
                    flow.mudarMicroEtapa("identificacao");
                  }}
                />
              )}
            </form>
          </Form>
        </CardContent>
      </Card>

      <TcleDialog open={tcleDialogOpen} onOpenChange={setTcleDialogOpen} />

      <SamuEmergencyModal
        open={flow.samuModalOpen}
        onOpenChange={flow.setSamuModalOpen}
        orientacoes={flow.orientacoesSamu}
        onCorrigirSintomas={flow.sintomaAcidental ? flow.corrigirAcidental : undefined}
        onConfirmarSaida={() => {
          flow.setSamuModalOpen(false);
          flow.setEncaminhadoPresencial(true);
        }}
      />
    </>
  );
}
