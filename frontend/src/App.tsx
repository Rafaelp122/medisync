import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { LiveKitTokenResponse, VerificarOtpResponse } from "@/api/generated/types.gen";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DoctorLoginCard } from "@/features/consultation/components/doctor-login-card";
import { DoctorWorkstation } from "@/features/consultation/components/doctor-workstation";
import type { AcolhimentoConcluidoData } from "@/features/onboarding/components/acolhimento-fase1-form";
import { AuthOtpCard } from "@/features/onboarding/components/auth-otp-card";
import { EnriquecimentoFase2Form } from "@/features/onboarding/components/enriquecimento-fase2-form";
import { IngressoConfirmadoCard } from "@/features/onboarding/components/ingresso-confirmado-card";
import { ProgressiveOnboardingWizard } from "@/features/onboarding/components/progressive-onboarding-wizard";
import { VirtualWaitingRoom } from "@/features/queue/components/virtual-waiting-room";
import {
  clearStoredDoctorSession,
  clearStoredSession,
  getStoredDoctorSession,
  getStoredSession,
  type StoredDoctorSession,
  type StoredPatientSession,
  saveStoredDoctorSession,
  saveStoredSession,
} from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { startSafeViewTransition } from "@/lib/view-transitions";

const queryClient = new QueryClient();

export function App() {
  const [session, setSession] = useState<StoredPatientSession | null>(() => getStoredSession());
  const [doctorSession, setDoctorSession] = useState<StoredDoctorSession | null>(() =>
    getStoredDoctorSession(),
  );
  const [modo, setModo] = useState<"acolhimento" | "otp" | "medico">(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const modeParam = params.get("mode");
      if (modeParam === "otp") {
        return "otp";
      }
      if (modeParam === "doctor" || modeParam === "medico") {
        return "medico";
      }
    }
    const storedDoctor = getStoredDoctorSession();
    if (storedDoctor) {
      return "medico";
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

  const [teleconsultaData, setTeleconsultaData] = useState<LiveKitTokenResponse | null>(null);
  const [modalComplementarAberto, setModalComplementarAberto] = useState(false);

  const handleAtendimentoIniciado = (data: LiveKitTokenResponse) => {
    setModalComplementarAberto(false);
    startSafeViewTransition(() => {
      setTeleconsultaData(data);
    });
  };

  const handleEncerrarSessao = () => {
    clearStoredSession();
    setModalComplementarAberto(false);
    startSafeViewTransition(() => {
      setTeleconsultaData(null);
      setSession(null);
      setModo("acolhimento");
    });
  };

  const handleDoctorLogin = (newDoctorSession: StoredDoctorSession) => {
    saveStoredDoctorSession(newDoctorSession);
    startSafeViewTransition(() => {
      setDoctorSession(newDoctorSession);
    });
  };

  const handleDoctorLogout = () => {
    clearStoredDoctorSession();
    startSafeViewTransition(() => {
      setDoctorSession(null);
    });
  };

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const modos: Array<"acolhimento" | "otp" | "medico"> = ["acolhimento", "otp", "medico"];
      const currentIndex = modos.indexOf(modo);
      const nextIndex =
        e.key === "ArrowRight"
          ? (currentIndex + 1) % modos.length
          : (currentIndex - 1 + modos.length) % modos.length;
      setModo(modos[nextIndex]);
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <main
        id="main-content"
        className="min-h-screen flex flex-col items-center justify-start p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-background text-foreground"
      >
        <header className="mb-4 text-center space-y-1">
          <h1 className="text-3xl font-extrabold tracking-tight text-primary text-balance">
            MediSync Express
          </h1>
          <p className="text-sm text-muted-foreground text-pretty">
            Pronto Atendimento Virtual & Telemedicina de Urgência
          </p>
        </header>

        {teleconsultaData ? (
          <div className="w-full max-w-xl mx-auto p-6 bg-card text-card-foreground rounded-xl shadow-lg border border-emerald-500/30 text-center space-y-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-2">
              <span className="text-3xl" aria-hidden="true">
                📹
              </span>
            </div>
            <h2 className="text-2xl font-bold text-foreground">Teleconsulta em Andamento</h2>
            <p className="text-xs text-muted-foreground">
              Conexão com a sala LiveKit estabelecida com sucesso.
            </p>
            <div className="p-3 bg-muted rounded-lg text-xs font-mono text-left space-y-1 border">
              <p>
                <strong>Sala:</strong> {teleconsultaData.room_name}
              </p>
              <p>
                <strong>Participante:</strong> {teleconsultaData.participant_identity}
              </p>
            </div>
            <button
              type="button"
              onClick={handleEncerrarSessao}
              className="min-h-[44px] px-4 py-2 border rounded-md text-xs font-semibold hover:bg-muted transition-colors"
            >
              Encerrar Teleconsulta
            </button>
          </div>
        ) : session ? (
          session.atendimentoId ? (
            <>
              <VirtualWaitingRoom
                session={session}
                onEncerrarSessao={handleEncerrarSessao}
                onAtendimentoIniciado={handleAtendimentoIniciado}
                onComplementarCadastro={() => setModalComplementarAberto(true)}
              />

              <Dialog open={modalComplementarAberto} onOpenChange={setModalComplementarAberto}>
                <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto p-0 border-0 bg-transparent shadow-none">
                  <DialogHeader className="sr-only">
                    <DialogTitle>Complementação Cadastral (Fase 2)</DialogTitle>
                    <DialogDescription>
                      Complemente seus dados de endereço e alergias para o prontuário médico. Sua
                      vaga na fila virtual permanece garantida.
                    </DialogDescription>
                  </DialogHeader>
                  <EnriquecimentoFase2Form
                    pacienteId={session.pacienteId}
                    token={session.token}
                    onConcluido={() => setModalComplementarAberto(false)}
                    onPular={() => setModalComplementarAberto(false)}
                  />
                </DialogContent>
              </Dialog>
            </>
          ) : (
            <IngressoConfirmadoCard session={session} onEncerrarSessao={handleEncerrarSessao} />
          )
        ) : (
          <div
            className={cn(
              "w-full mx-auto space-y-4",
              modo === "medico" ? "max-w-[1600px]" : "max-w-xl",
            )}
          >
            {!doctorSession && (
              <div className="flex justify-center">
                <div
                  role="tablist"
                  aria-label="Opções de atendimento"
                  onKeyDown={handleTabKeyDown}
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
                  <button
                    type="button"
                    id="tab-medico"
                    role="tab"
                    aria-selected={modo === "medico"}
                    aria-controls="panel-medico"
                    onClick={() => setModo("medico")}
                    className={cn(
                      "min-h-[44px] px-3.5 py-2 rounded-md font-medium transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      modo === "medico"
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    Estação Médica (Dr. Eduardo Rocha)
                  </button>
                </div>
              </div>
            )}

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

            <div
              role="tabpanel"
              id="panel-medico"
              aria-labelledby="tab-medico"
              hidden={modo !== "medico"}
            >
              {modo === "medico" &&
                (!doctorSession ? (
                  <DoctorLoginCard onLoginSuccess={handleDoctorLogin} />
                ) : (
                  <DoctorWorkstation
                    token={doctorSession.token}
                    medicoId={doctorSession.medicoId}
                    medicoNome={doctorSession.medicoNome}
                    crmUf={doctorSession.crmUf}
                    onLogout={handleDoctorLogout}
                  />
                ))}
            </div>
          </div>
        )}
      </main>
    </QueryClientProvider>
  );
}

export default App;
