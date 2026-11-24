import { type ReactNode, useState } from "react";
import type { ConfigPlantaoRequest } from "@/api/generated/types.gen";
import { cn } from "@/lib/utils";
import { useAtualizarConfigPlantao, useConfigPlantao } from "../api/use-telemetria-painel";
import { ConfigPlantaoCard } from "./painel/config-plantao-card";
import { PainelMetricasAoVivo } from "./painel/painel-metricas-ao-vivo";

export interface PainelGestorProps {
  gestorNome?: string;
  onLogout?: () => void;
  renderBpaCard?: ReactNode;
  className?: string;
}

/**
 * Painel de Regulação e Telemetria SUS em Tempo Real (RF-09, RN06).
 * Isola o polling de 5s em `PainelMetricasAoVivo` para proteger o formulário de
 * configuração e a exportação ambulatorial BPA-I de re-renderizações desnecessárias.
 */
export function PainelGestor({
  gestorNome = "Gestor da Unidade",
  onLogout,
  renderBpaCard,
  className,
}: PainelGestorProps) {
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const { data: config } = useConfigPlantao();
  const {
    mutate: atualizarConfig,
    isPending: isSubmittingConfig,
    error: configError,
  } = useAtualizarConfigPlantao();

  const handleSubmitConfig = (payload: ConfigPlantaoRequest) => {
    setSuccessMessage(null);
    atualizarConfig(payload, {
      onSuccess: () => {
        setSuccessMessage("Política do plantão atualizada com sucesso.");
      },
    });
  };

  return (
    <div className={cn("w-full max-w-7xl mx-auto space-y-4 p-2 sm:p-4 text-foreground", className)}>
      <PainelMetricasAoVivo gestorNome={gestorNome} config={config} onLogout={onLogout} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <ConfigPlantaoCard
          config={config}
          isSubmitting={isSubmittingConfig}
          error={configError}
          successMessage={successMessage}
          onSubmitConfig={handleSubmitConfig}
        />
        {renderBpaCard}
      </div>
    </div>
  );
}
