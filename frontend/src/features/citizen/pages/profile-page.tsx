import { CheckCircle2, ShieldAlert } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { DependentsSection } from "@/features/citizen/components/dependents-section";
import { ProfilePasskeySection } from "@/features/citizen/components/profile-passkey-section";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";

export interface ProfilePageProps {
  session?: StoredPatientSession | null;
  renderEnrichmentForm?: (props: {
    pacienteId: string;
    token: string;
    onConcluido: () => void;
  }) => ReactNode;
}

/**
 * Página de Perfil, Dados CFM, Dependentes e Passkey do Cidadão (`/perfil`).
 * Aceita composição via render prop `renderEnrichmentForm` para injeção de `EnriquecimentoFase2Form`
 * pela rota sem violar fronteiras entre features, e exibe sempre o gerenciamento de Passkeys.
 */
export function ProfilePage({ session, renderEnrichmentForm }: ProfilePageProps) {
  const activeSession = session ?? getStoredSession();
  const [enrichmentConcluido, setEnrichmentConcluido] = useState(false);

  const pacienteId = activeSession?.pacienteId ?? "";
  const token = activeSession?.token ?? "";

  return (
    <CitizenShellLayout session={activeSession}>
      <div className="space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Perfil e Dependentes
          </h1>
          <p className="text-sm text-muted-foreground">
            Complete seu cadastro regulatório CFM, gerencie dependentes familiares e ative o acesso
            biométrico Passkey.
          </p>
        </header>

        {!pacienteId ? (
          <Alert variant="destructive">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Sessão do cidadão não identificada</AlertTitle>
            <AlertDescription>
              Entre novamente no Portal do Cidadão para visualizar e atualizar seu perfil e
              dependentes.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="space-y-6">
            {enrichmentConcluido && (
              <Alert>
                <CheckCircle2 className="h-4 w-4 text-primary" aria-hidden="true" />
                <AlertTitle>Cadastro CFM concluído</AlertTitle>
                <AlertDescription>
                  Seus dados cadastrais e endereço foram atualizados no prontuário.
                </AlertDescription>
              </Alert>
            )}

            {renderEnrichmentForm && (
              <section aria-label="Completar dados cadastrais CFM">
                {renderEnrichmentForm({
                  pacienteId,
                  token,
                  onConcluido: () => setEnrichmentConcluido(true),
                })}
              </section>
            )}

            <DependentsSection pacienteId={pacienteId} token={token} />

            <section aria-label="Gerenciar biometria Passkey">
              <ProfilePasskeySection token={token} />
            </section>
          </div>
        )}
      </div>
    </CitizenShellLayout>
  );
}

export default ProfilePage;
