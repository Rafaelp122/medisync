import { useState } from "react";
import { isThreePartJwt, type StoredPatientSession } from "@/lib/session-storage";
import { startSafeViewTransition } from "@/lib/view-transitions";
import { type AcolhimentoConcluidoData, AcolhimentoFase1Form } from "./acolhimento-fase1-form";
import { AuthenticatedTriagemFlow } from "./authenticated-triagem-flow";
import { EnriquecimentoFase2Form } from "./enriquecimento-fase2-form";

export type { AcolhimentoConcluidoData };
export type EtapaWizard = "acolhimento" | "enriquecimento";

export interface ProgressiveOnboardingWizardProps {
  session?: StoredPatientSession | null;
  onTrocarParaOtp?: () => void;
  onSessaoIniciada?: (data: AcolhimentoConcluidoData) => void;
  onFinalizar?: (data: AcolhimentoConcluidoData) => void;
}

/**
 * Orquestrador da jornada de Triagem + Enriquecimento.
 * Cidadãos com JWT 3-partes seguem diretamente pela triagem clínica sem re-identificação.
 */
export function ProgressiveOnboardingWizard({
  session,
  onTrocarParaOtp,
  onSessaoIniciada,
  onFinalizar,
}: ProgressiveOnboardingWizardProps) {
  const [etapa, setEtapa] = useState<EtapaWizard>("acolhimento");
  const [admissaoData, setAdmissaoData] = useState<AcolhimentoConcluidoData | null>(null);

  if (session?.pacienteId && isThreePartJwt(session.token)) {
    return (
      <AuthenticatedTriagemFlow
        session={session}
        onSessaoIniciada={onSessaoIniciada}
        onFinalizar={onFinalizar}
      />
    );
  }

  const handleAcolhimentoConcluido = (data: AcolhimentoConcluidoData) => {
    setAdmissaoData(data);
    onSessaoIniciada?.(data);
    startSafeViewTransition(() => {
      setEtapa("enriquecimento");
    });
  };

  const handleEnriquecimentoConcluido = () => {
    if (admissaoData) {
      onFinalizar?.(admissaoData);
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
