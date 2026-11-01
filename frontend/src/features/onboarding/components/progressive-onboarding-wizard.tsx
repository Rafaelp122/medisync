import { useState } from "react";
import { startSafeViewTransition } from "@/lib/view-transitions";
import { type AcolhimentoConcluidoData, AcolhimentoFase1Form } from "./acolhimento-fase1-form";
import { EnriquecimentoFase2Form } from "./enriquecimento-fase2-form";

export type EtapaWizard = "acolhimento" | "enriquecimento";

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
    startSafeViewTransition(() => {
      setEtapa(proxima);
    });
  };

  const handleAcolhimentoConcluido = (data: AcolhimentoConcluidoData) => {
    setAdmissaoData(data);
    if (onSessaoIniciada) {
      onSessaoIniciada(data);
    }
    transicionar("enriquecimento");
  };

  const handleEnriquecimentoConcluido = () => {
    if (admissaoData && onFinalizar) {
      onFinalizar(admissaoData);
    }
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
        onPular={handleEnriquecimentoConcluido}
      />
    );
  }

  return null;
}
