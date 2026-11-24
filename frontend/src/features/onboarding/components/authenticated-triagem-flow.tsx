import { useState } from "react";
import { SamuEmergencyModal } from "@/components/samu-emergency-modal";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Form } from "@/components/ui/form";
import type { StoredPatientSession } from "@/lib/session-storage";
import { useAcolhimentoTriagemFlow } from "../hooks/use-acolhimento-triagem-flow";
import type { AcolhimentoConcluidoData } from "./acolhimento-fase1-form";
import { EnriquecimentoFase2Form } from "./enriquecimento-fase2-form";
import { SamuPresencialRedirectCard } from "./samu-presencial-redirect-card";
import { TcleDialog } from "./tcle-dialog";
import { TriageClinicalStep } from "./triage-clinical-step";

export interface AuthenticatedTriagemFlowProps {
  session: StoredPatientSession;
  onSessaoIniciada?: (data: AcolhimentoConcluidoData) => void;
  onFinalizar?: (data: AcolhimentoConcluidoData) => void;
}

/**
 * Fluxo direto de triagem para cidadão autenticado (JWT 3-partes),
 * evitando re-identificação e sobrescrita de token por intake_token.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function AuthenticatedTriagemFlow({
  session,
  onSessaoIniciada,
  onFinalizar,
}: AuthenticatedTriagemFlowProps) {
  const [tcleDialogOpen, setTcleDialogOpen] = useState(false);

  const flow = useAcolhimentoTriagemFlow({
    session,
    onAdmitted: (admissaoRes) => {
      onSessaoIniciada?.({
        pacienteId: admissaoRes.paciente_id,
        atendimentoId: admissaoRes.atendimento_id,
        token: session.token,
        prioridadeClinica: admissaoRes.prioridade_clinica,
        isNovoPaciente: false,
      });
    },
  });

  if (flow.step === "samu_redirect") {
    return (
      <SamuPresencialRedirectCard
        orientacoes={flow.samuOrientacoes}
        onReiniciar={flow.reiniciarTriagem}
      />
    );
  }

  if (flow.step === "enrichment" && flow.admissaoConcluida) {
    const concluidoData: AcolhimentoConcluidoData = {
      pacienteId: flow.admissaoConcluida.paciente_id,
      atendimentoId: flow.admissaoConcluida.atendimento_id,
      token: session.token,
      prioridadeClinica: flow.admissaoConcluida.prioridade_clinica,
      isNovoPaciente: false,
    };
    const finalizar = () => onFinalizar?.(concluidoData);

    return (
      <EnriquecimentoFase2Form
        pacienteId={session.pacienteId}
        token={session.token}
        onConcluido={finalizar}
        onPular={finalizar}
      />
    );
  }

  const sintomas = flow.form.watch("sintomas") ?? [];
  const escalaDor = flow.form.watch("escala_dor") ?? 0;
  const tcleAceito = Boolean(flow.form.watch("aceite_tcle"));

  return (
    <>
      <Card className="w-full max-w-xl mx-auto shadow-md">
        <CardHeader className="space-y-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-primary">
            Triagem Clínica • Cidadão Identificado
          </span>
          <CardTitle className="text-2xl font-bold">Pronto Atendimento Virtual</CardTitle>
          <CardDescription>
            Conte-nos o que você está sentindo e informe a intensidade dos sintomas.
          </CardDescription>
        </CardHeader>

        <CardContent>
          {flow.erroHumanizado && (
            <Alert variant="destructive" className="mb-4" role="alert">
              <AlertTitle className="font-bold">{flow.erroHumanizado.title}</AlertTitle>
              <AlertDescription className="mt-1 text-sm leading-relaxed">
                {flow.erroHumanizado.detail}
              </AlertDescription>
            </Alert>
          )}

          <Form {...flow.form}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void flow.submitTriagem();
              }}
              className="space-y-4"
            >
              <TriageClinicalStep
                control={flow.form.control}
                sintomasSelecionados={sintomas}
                escalaDor={escalaDor}
                tcleAceito={tcleAceito}
                isSubmitting={flow.isSubmitting}
                onToggleSintoma={flow.selecionarSintoma}
                onEscalaDorChange={(val) => flow.form.setValue("escala_dor", val)}
                onTcleChange={(checked) =>
                  flow.form.setValue("aceite_tcle", checked, { shouldValidate: true })
                }
                onAbrirTcle={() => setTcleDialogOpen(true)}
              />
            </form>
          </Form>
        </CardContent>
      </Card>

      <TcleDialog open={tcleDialogOpen} onOpenChange={setTcleDialogOpen} />

      <SamuEmergencyModal
        open={flow.samuModalOpen}
        onOpenChange={flow.setSamuModalOpen}
        orientacoes={flow.samuOrientacoes}
        onCorrigirSintomas={flow.sintomaAcidental ? flow.corrigirSintomaAcidental : undefined}
        onConfirmarSaida={flow.confirmarSaidaSamu}
      />
    </>
  );
}
