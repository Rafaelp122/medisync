import { Building2, HeartPulse, Stethoscope } from "lucide-react";
import { useState } from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import type {
  StoredDoctorSession,
  StoredManagerSession,
  StoredPatientSession,
} from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { CadsusLoginForm } from "./cadsus-login-form";
import { DoctorLoginForm } from "./doctor-login-form";
import { ManagerLoginForm } from "./manager-login-form";

export type PerfilAuth = "cidadao" | "medico" | "gestor";

export interface TripartiteAuthCardProps {
  initialPerfil?: PerfilAuth;
  onPatientAuthenticated: (session: StoredPatientSession) => void;
  onDoctorAuthenticated: (session: StoredDoctorSession) => void;
  onManagerAuthenticated: (session: StoredManagerSession) => void;
  onAlternarOtp?: () => void;
  className?: string;
}

export function TripartiteAuthCard({
  initialPerfil = "cidadao",
  onPatientAuthenticated,
  onDoctorAuthenticated,
  onManagerAuthenticated,
  onAlternarOtp,
  className,
}: TripartiteAuthCardProps) {
  const [perfil, setPerfil] = useState<PerfilAuth>(initialPerfil);

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const perfis: PerfilAuth[] = ["cidadao", "medico", "gestor"];
      const currentIndex = perfis.indexOf(perfil);
      const nextIndex =
        e.key === "ArrowRight"
          ? (currentIndex + 1) % perfis.length
          : (currentIndex - 1 + perfis.length) % perfis.length;
      setPerfil(perfis[nextIndex]);
    }
  };

  const handleCadsusSuccess = (data: VerificarOtpResponse) => {
    const patientSession: StoredPatientSession = {
      tipo: "otp",
      role: data.role ?? "PACIENTE",
      pacienteId: data.paciente_id,
      token: data.access_token,
    };
    onPatientAuthenticated(patientSession);
  };

  return (
    <div className={cn("w-full max-w-md mx-auto space-y-4", className)}>
      {/* Seletor Tripartito de Perfis */}
      <div className="flex justify-center">
        <div
          role="tablist"
          aria-label="Seleção de perfil de acesso SUS"
          onKeyDown={handleTabKeyDown}
          className="inline-flex gap-1 p-1 bg-muted rounded-xl text-xs sm:text-sm w-full"
        >
          <button
            type="button"
            id="tab-cidadao"
            role="tab"
            aria-selected={perfil === "cidadao"}
            aria-controls="panel-cidadao"
            onClick={() => setPerfil("cidadao")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 min-h-[44px] py-2 px-2.5 rounded-lg font-semibold transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-center",
              perfil === "cidadao"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <HeartPulse className="size-4 shrink-0 text-emerald-600" />
            <span>Cidadão</span>
          </button>

          <button
            type="button"
            id="tab-medico"
            role="tab"
            aria-selected={perfil === "medico"}
            aria-controls="panel-medico"
            onClick={() => setPerfil("medico")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 min-h-[44px] py-2 px-2.5 rounded-lg font-semibold transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-center",
              perfil === "medico"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Stethoscope className="size-4 shrink-0 text-primary" />
            <span>Médico</span>
          </button>

          <button
            type="button"
            id="tab-gestor"
            role="tab"
            aria-selected={perfil === "gestor"}
            aria-controls="panel-gestor"
            onClick={() => setPerfil("gestor")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 min-h-[44px] py-2 px-2.5 rounded-lg font-semibold transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-center",
              perfil === "gestor"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Building2 className="size-4 shrink-0 text-amber-500" />
            <span>Gestor</span>
          </button>
        </div>
      </div>

      {/* Painéis de Conteúdo */}
      <div
        role="tabpanel"
        id="panel-cidadao"
        aria-labelledby="tab-cidadao"
        hidden={perfil !== "cidadao"}
      >
        {perfil === "cidadao" && (
          <CadsusLoginForm onSuccess={handleCadsusSuccess} onAlternarOtp={onAlternarOtp} />
        )}
      </div>

      <div
        role="tabpanel"
        id="panel-medico"
        aria-labelledby="tab-medico"
        hidden={perfil !== "medico"}
      >
        {perfil === "medico" && <DoctorLoginForm onLoginSuccess={onDoctorAuthenticated} />}
      </div>

      <div
        role="tabpanel"
        id="panel-gestor"
        aria-labelledby="tab-gestor"
        hidden={perfil !== "gestor"}
      >
        {perfil === "gestor" && <ManagerLoginForm onLoginSuccess={onManagerAuthenticated} />}
      </div>
    </div>
  );
}

export default TripartiteAuthCard;
