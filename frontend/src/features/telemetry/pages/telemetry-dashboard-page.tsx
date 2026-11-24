import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { client } from "@/api/client";
import { logoutApiV1AuthLogoutPost } from "@/api/generated/sdk.gen";
import { PainelGestor } from "@/features/telemetry/components/painel-gestor";
import type { StoredManagerSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";

export interface TelemetryDashboardPageProps {
  managerSession: StoredManagerSession;
  renderBpaCard?: ReactNode;
}

export function TelemetryDashboardPage({
  managerSession,
  renderBpaCard,
}: TelemetryDashboardPageProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleManagerLogout = async () => {
    try {
      await logoutApiV1AuthLogoutPost({ client, body: {} });
    } catch {
      // Falha de rede não impede expurgo local
    }
    sessionTransport.clearSession("staff");
    queryClient.clear();
    navigate({ to: "/interno/login" });
  };

  return (
    <PainelGestor
      gestorNome={managerSession.nome}
      onLogout={handleManagerLogout}
      renderBpaCard={renderBpaCard}
    />
  );
}
