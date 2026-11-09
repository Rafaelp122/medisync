import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import type { LiveKitTokenResponse, VerificarOtpResponse } from "@/api/generated/types.gen";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  type PerfilAuth,
  TripartiteAuthCard,
} from "@/features/auth/components/tripartite-auth-card";
import { DoctorWorkstation } from "@/features/consultation/components/doctor-workstation";
import { PosConsultaSummary } from "@/features/consultation/components/pos-consulta-summary";
import type { AcolhimentoConcluidoData } from "@/features/onboarding/components/acolhimento-fase1-form";
import { AuthOtpCard } from "@/features/onboarding/components/auth-otp-card";
import { EnriquecimentoFase2Form } from "@/features/onboarding/components/enriquecimento-fase2-form";
import { IngressoConfirmadoCard } from "@/features/onboarding/components/ingresso-confirmado-card";
import { ProgressiveOnboardingWizard } from "@/features/onboarding/components/progressive-onboarding-wizard";
import { VirtualWaitingRoom } from "@/features/queue/components/virtual-waiting-room";
import { PainelGestor } from "@/features/telemetry/components/painel-gestor";
import {
  clearStoredDoctorSession,
  clearStoredManagerSession,
  clearStoredSession,
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
  type StoredDoctorSession,
  type StoredManagerSession,
  type StoredPatientSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
  saveStoredSession,
} from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { startSafeViewTransition } from "@/lib/view-transitions";

const LazyLiveKitVideoCall = lazy(
  () => import("@/features/consultation/components/livekit-video-call"),
);

const queryClient = new QueryClient();

type AppModo = "acolhimento" | "otp" | "login";

export function App() {
  const [session, setSession] = useState<StoredPatientSession | null>(() => getStoredSession());
  const [doctorSession, setDoctorSession] = useState<StoredDoctorSession | null>(() =>
    getStoredDoctorSession(),
  );
  const [managerSession, setManagerSession] = useState<StoredManagerSession | null>(() =>
    getStoredManagerSession(),
  );

  const [initialPerfil] = useState<PerfilAuth>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const modeParam = params.get("mode");
      if (modeParam === "doctor" || modeParam === "medico") return "medico";
      if (modeParam === "gestor" || modeParam === "manager") return "gestor";
      if (modeParam === "cadsus") return "cidadao";
    }
    return "cidadao";
  });

  const [modo, setModo] = useState<AppModo>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const modeParam = params.get("mode");
      if (modeParam === "otp") return "otp";
      if (
        modeParam === "login" ||
        modeParam === "cadsus" ||
        modeParam === "doctor" ||
        modeParam === "medico" ||
        modeParam === "gestor" ||
        modeParam === "manager"
      ) {
        return "login";
      }
    }
    const storedDoctor = getStoredDoctorSession();
    if (storedDoctor) return "login";
    const storedManager = getStoredManagerSession();
    if (storedManager) return "login";
    return "acolhimento";
  });

  const [teleconsultaData, setTeleconsultaData] = useState<LiveKitTokenResponse | null>(null);
  const [teleconsultaFinalizada, setTeleconsultaFinalizada] = useState(false);
  const [modalComplementarAberto, setModalComplementarAberto] = useState(false);

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

  const handlePatientAuthenticated = (patientSession: StoredPatientSession) => {
    saveStoredSession(patientSession);
    startSafeViewTransition(() => {
      setSession(patientSession);
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
      status: "APTO_PARA_CHAMADA",
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
      status: "APTO_PARA_CHAMADA",
    };
    saveStoredSession(newSession);
    startSafeViewTransition(() => {
      setSession(newSession);
    });
  };

  const handleAtendimentoIniciado = (data: LiveKitTokenResponse) => {
    setModalComplementarAberto(false);
    setTeleconsultaFinalizada(false);
    startSafeViewTransition(() => {
      setTeleconsultaData(data);
    });
  };

  const handleTeleconsultaEncerrada = () => {
    startSafeViewTransition(() => {
      setTeleconsultaData(null);
      setTeleconsultaFinalizada(true);
    });
  };

  const handleEncerrarSessao = () => {
    clearStoredSession();
    setModalComplementarAberto(false);
    startSafeViewTransition(() => {
      setTeleconsultaData(null);
      setTeleconsultaFinalizada(false);
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

  const handleManagerLogin = (newManagerSession: StoredManagerSession) => {
    saveStoredManagerSession(newManagerSession);
    startSafeViewTransition(() => {
      setManagerSession(newManagerSession);
    });
  };

  const handleManagerLogout = () => {
    clearStoredManagerSession();
    startSafeViewTransition(() => {
      setManagerSession(null);
    });
  };

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const modos: AppModo[] = ["acolhimento", "otp", "login"];
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

        {managerSession ? (
          <PainelGestor
            token={managerSession.token}
            gestorNome={managerSession.nome}
            onLogout={handleManagerLogout}
          />
        ) : doctorSession ? (
          <div className="w-full max-w-[1600px] mx-auto">
            <DoctorWorkstation
              token={doctorSession.token}
              medicoId={doctorSession.medicoId}
              medicoNome={doctorSession.medicoNome}
              crmUf={doctorSession.crmUf}
              onLogout={handleDoctorLogout}
            />
          </div>
        ) : teleconsultaFinalizada && session?.atendimentoId ? (
          <PosConsultaSummary
            atendimentoId={session.atendimentoId}
            token={session.token}
            onNovaConsulta={handleEncerrarSessao}
          />
        ) : teleconsultaData ? (
          <div className="w-full max-w-2xl mx-auto space-y-4">
            <Suspense
              fallback={
                <div className="h-80 flex items-center justify-center bg-slate-900 rounded-xl text-slate-300 text-xs">
                  Conectando à Sala de Teleconsulta LiveKit SFU…
                </div>
              }
            >
              <LazyLiveKitVideoCall
                wsUrl={teleconsultaData.ws_url}
                token={teleconsultaData.token}
                roomName={teleconsultaData.room_name}
                participantName={teleconsultaData.participant_identity}
                remoteParticipantName="Dr. Eduardo Rocha (Médico Plantonista)"
                onDisconnected={handleTeleconsultaEncerrada}
                className="min-h-[420px]"
              />
            </Suspense>
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
          <div className="w-full max-w-xl mx-auto space-y-4">
            <div className="flex justify-center overflow-x-auto pb-1">
              <div
                role="tablist"
                aria-label="Opções de atendimento"
                onKeyDown={handleTabKeyDown}
                className="inline-flex flex-wrap gap-1 p-1 bg-muted rounded-xl text-xs sm:text-sm"
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
                  id="tab-login"
                  role="tab"
                  aria-selected={modo === "login"}
                  aria-controls="panel-login"
                  onClick={() => setModo("login")}
                  className={cn(
                    "min-h-[44px] px-3.5 py-2 rounded-md font-medium transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    modo === "login"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Acesso por Perfil (SUS)
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

            <div
              role="tabpanel"
              id="panel-login"
              aria-labelledby="tab-login"
              hidden={modo !== "login"}
            >
              {modo === "login" && (
                <div className="max-w-md mx-auto">
                  <TripartiteAuthCard
                    initialPerfil={initialPerfil}
                    onPatientAuthenticated={handlePatientAuthenticated}
                    onDoctorAuthenticated={handleDoctorLogin}
                    onManagerAuthenticated={handleManagerLogin}
                    onAlternarOtp={() => setModo("otp")}
                  />
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
