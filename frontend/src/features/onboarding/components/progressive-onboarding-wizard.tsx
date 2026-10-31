import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type AcolhimentoConcluidoData, AcolhimentoFase1Form } from "./acolhimento-fase1-form";
import { EnriquecimentoFase2Form } from "./enriquecimento-fase2-form";

export type EtapaWizard = "acolhimento" | "enriquecimento" | "concluido";

export interface ProgressiveOnboardingWizardProps {
  onTrocarParaOtp?: () => void;
  onSessaoIniciada?: (data: AcolhimentoConcluidoData) => void;
  onFinalizar?: (data: AcolhimentoConcluidoData) => void;
}

export function ProgressiveOnboardingWizard({
  onTrocarParaOtp,
  onSessaoIniciada,
  onFinalizar,
}: ProgressiveOnboardingWizardProps) {
  const [etapa, setEtapa] = useState<EtapaWizard>("acolhimento");
  const [admissaoData, setAdmissaoData] = useState<AcolhimentoConcluidoData | null>(null);

  const transicionar = (proxima: EtapaWizard) => {
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!prefersReducedMotion && "startViewTransition" in document) {
      document.startViewTransition(() => {
        setEtapa(proxima);
      });
    } else {
      setEtapa(proxima);
    }
  };

  const handleAcolhimentoConcluido = (data: AcolhimentoConcluidoData) => {
    setAdmissaoData(data);
    if (onSessaoIniciada) {
      onSessaoIniciada(data);
    }
    transicionar("enriquecimento");
  };

  const handleEnriquecimentoConcluido = () => {
    transicionar("concluido");
  };

  if (etapa === "acolhimento") {
    return (
      <AcolhimentoFase1Form
        onAdmissaoConcluida={handleAcolhimentoConcluido}
        onVoltarParaLogin={onTrocarParaOtp}
      />
    );
  }

  if (etapa === "enriquecimento" && admissaoData) {
    return (
      <EnriquecimentoFase2Form
        pacienteId={admissaoData.pacienteId}
        token={admissaoData.token}
        onConcluido={handleEnriquecimentoConcluido}
        onPular={() => transicionar("concluido")}
      />
    );
  }

  return (
    <Card className="w-full max-w-md mx-auto shadow-lg text-center space-y-4">
      <CardHeader>
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-2">
          <span className="text-3xl" aria-hidden="true">
            ✓
          </span>
        </div>
        <CardTitle className="text-2xl font-bold text-primary">Ingresso Confirmado!</CardTitle>
        <CardDescription>
          Você já está posicionado na fila virtual de espera do Pronto Atendimento.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-left">
        <div className="p-4 bg-muted/50 rounded-lg text-xs font-mono space-y-1.5 border">
          <p>
            <strong>Atendimento ID:</strong> {admissaoData?.atendimentoId}
          </p>
          <p>
            <strong>Prioridade Clínica:</strong> Nível {admissaoData?.prioridadeClinica} (ACR)
          </p>
          <p>
            <strong>Status:</strong> TRIADO_AGUARDANDO_ELEGIBILIDADE
          </p>
        </div>

        <p className="text-sm text-muted-foreground leading-relaxed">
          Nossa equipe médica está ciente e sua chamada será iniciada em instantes. Mantenha esta
          tela aberta para receber a notificação de chamada com áudio e vídeo.
        </p>

        {admissaoData && onFinalizar && (
          <Button
            type="button"
            className="w-full font-bold"
            onClick={() => onFinalizar(admissaoData)}
          >
            Acompanhar Atendimento na Fila
          </Button>
        )}

        {onTrocarParaOtp && (
          <Button type="button" variant="outline" className="w-full mt-2" onClick={onTrocarParaOtp}>
            Acessar com outro número
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
