import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import type { AcolhimentoConcluidoData } from "@/features/onboarding/components/acolhimento-fase1-form";
import { AuthOtpCard } from "@/features/onboarding/components/auth-otp-card";
import { ProgressiveOnboardingWizard } from "@/features/onboarding/components/progressive-onboarding-wizard";
import { cn } from "@/lib/utils";

const queryClient = new QueryClient();

export interface AppSessionData {
  tipo: "otp" | "acolhimento";
  role: string;
  pacienteId: string;
  atendimentoId?: string;
  prioridadeClinica?: number;
  token?: string;
}

export function App() {
  const [session, setSession] = useState<AppSessionData | null>(null);
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
    setSession({
      tipo: "otp",
      role: data.role,
      pacienteId: data.paciente_id,
      token: data.token,
    });
  };

  const handleOnboardingFinalizado = (data: AcolhimentoConcluidoData) => {
    setSession({
      tipo: "acolhimento",
      role: "PACIENTE",
      pacienteId: data.pacienteId,
      atendimentoId: data.atendimentoId,
      prioridadeClinica: data.prioridadeClinica,
      token: data.token,
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
          <div className="w-full max-w-md mx-auto p-6 bg-card rounded-xl border shadow text-center space-y-4">
            <h2 className="text-2xl font-bold text-primary text-balance">Acesso Autorizado</h2>
            <p className="text-sm text-muted-foreground text-pretty">
              {session.tipo === "acolhimento"
                ? "Atendimento admitido na fila virtual com sucesso."
                : "Sessão de paciente autenticada com sucesso via SMS."}
            </p>
            <div className="p-3 bg-muted rounded-md text-xs font-mono text-left break-all space-y-1">
              <p>
                <strong>Papel:</strong> {session.role}
              </p>
              <p>
                <strong>Paciente ID:</strong> {session.pacienteId}
              </p>
              {session.atendimentoId && (
                <p>
                  <strong>Atendimento ID:</strong> {session.atendimentoId}
                </p>
              )}
              {session.prioridadeClinica !== undefined && (
                <p>
                  <strong>Prioridade Clínica:</strong> Nível {session.prioridadeClinica} (ACR)
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => {
                setSession(null);
              }}
              className="inline-flex items-center justify-center min-h-[44px] px-3 py-2 text-xs text-muted-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
            >
              Encerrar sessão
            </button>
          </div>
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
                  Novo Atendimento (Acolhimento Rápido)
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
                  Acesso por Telefone / OTP
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
