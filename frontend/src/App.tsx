import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import type { AcolhimentoConcluidoData } from "@/features/onboarding/components/acolhimento-fase1-form";
import { AuthOtpCard } from "@/features/onboarding/components/auth-otp-card";
import { IngressoConfirmadoCard } from "@/features/onboarding/components/ingresso-confirmado-card";
import { ProgressiveOnboardingWizard } from "@/features/onboarding/components/progressive-onboarding-wizard";
import {
  clearStoredSession,
  getStoredSession,
  type StoredPatientSession,
  saveStoredSession,
} from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { startSafeViewTransition } from "@/lib/view-transitions";

const queryClient = new QueryClient();

export function App() {
  const [session, setSession] = useState<StoredPatientSession | null>(() => getStoredSession());
  const [modo, setModo] = useState<"acolhimento" | "otp">(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("mode") === "otp") {
        return "otp";
      }
    }
    return "acolhimento";
  });

  const handleOtpAuthenticated = (data: VerificarOtpResponse) => {
    const newSession: StoredPatientSession = {
      tipo: "otp",
      role: data.role ?? "PACIENTE",
      pacienteId: data.paciente_id,
      token: data.access_token,
    };
    saveStoredSession(newSession);
    startSafeViewTransition(() => {
      setSession(newSession);
    });
  };

  const handleSessaoIniciada = (data: AcolhimentoConcluidoData) => {
    // Persistência atômica no storage local após Admissão na Fila (Fase 1 concluída)
    const newSession: StoredPatientSession = {
      tipo: "acolhimento",
      role: "PACIENTE",
      pacienteId: data.pacienteId,
      atendimentoId: data.atendimentoId,
      prioridadeClinica: data.prioridadeClinica,
      token: data.token,
      status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
    };
    saveStoredSession(newSession);
  };

  const handleOnboardingFinalizado = (data: AcolhimentoConcluidoData) => {
    const newSession: StoredPatientSession = {
      tipo: "acolhimento",
      role: "PACIENTE",
      pacienteId: data.pacienteId,
      atendimentoId: data.atendimentoId,
      prioridadeClinica: data.prioridadeClinica,
      token: data.token,
      status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
    };
    saveStoredSession(newSession);
    startSafeViewTransition(() => {
      setSession(newSession);
    });
  };

  const handleEncerrarSessao = () => {
    clearStoredSession();
    startSafeViewTransition(() => {
      setSession(null);
      setModo("acolhimento");
    });
  };

  return (
    <QueryClientProvider client={queryClient}>
      <main
        id="main-content"
        className="min-h-screen flex flex-col items-center justify-center p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-background text-foreground"
      >
        <header className="mb-6 text-center space-y-1">
          <h1 className="text-3xl font-extrabold tracking-tight text-primary text-balance">
            MediSync Express
          </h1>
          <p className="text-sm text-muted-foreground text-pretty">
            Pronto Atendimento Virtual & Telemedicina de Urgência
          </p>
        </header>

        {session ? (
          <IngressoConfirmadoCard session={session} onEncerrarSessao={handleEncerrarSessao} />
        ) : (
          <div className="w-full max-w-xl mx-auto space-y-4">
            <div className="flex justify-center">
              <div
                role="tablist"
                aria-label="Opções de atendimento"
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                    e.preventDefault();
                    setModo((prev) => (prev === "acolhimento" ? "otp" : "acolhimento"));
                  }
                }}
                className="inline-flex gap-1 p-1 bg-muted rounded-lg text-xs sm:text-sm"
              >
                <button
                  type="button"
                  id="tab-acolhimento"
                  role="tab"
                  aria-selected={modo === "acolhimento"}
                  aria-controls="panel-acolhimento"
                  onClick={() => setModo("acolhimento")}
                  className={cn(
                    "min-h-[44px] px-3.5 py-2 rounded-md font-medium transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    modo === "acolhimento"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Novo Atendimento (Primeira Vez)
                </button>
                <button
                  type="button"
                  id="tab-otp"
                  role="tab"
                  aria-selected={modo === "otp"}
                  aria-controls="panel-otp"
                  onClick={() => setModo("otp")}
                  className={cn(
                    "min-h-[44px] px-3.5 py-2 rounded-md font-medium transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    modo === "otp"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Já tenho Atendimento (Telefone)
                </button>
              </div>
            </div>

            <div
              role="tabpanel"
              id="panel-acolhimento"
              aria-labelledby="tab-acolhimento"
              hidden={modo !== "acolhimento"}
            >
              {modo === "acolhimento" && (
                <ProgressiveOnboardingWizard
                  onTrocarParaOtp={() => setModo("otp")}
                  onSessaoIniciada={handleSessaoIniciada}
                  onFinalizar={handleOnboardingFinalizado}
                />
              )}
            </div>

            <div role="tabpanel" id="panel-otp" aria-labelledby="tab-otp" hidden={modo !== "otp"}>
              {modo === "otp" && (
                <div className="max-w-md mx-auto">
                  <AuthOtpCard onAuthenticated={handleOtpAuthenticated} />
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </QueryClientProvider>
  );
}

export default App;
