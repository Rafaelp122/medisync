import { Building2, Stethoscope } from "lucide-react";
import { useState } from "react";
import type { StoredDoctorSession, StoredManagerSession } from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { DoctorLoginForm } from "./doctor-login-form";
import { ManagerLoginForm } from "./manager-login-form";

export type PerfilStaffAuth = "medico" | "gestor";

export interface StaffAuthCardProps {
  initialPerfil?: PerfilStaffAuth;
  onDoctorAuthenticated: (session: StoredDoctorSession) => void;
  onManagerAuthenticated: (session: StoredManagerSession) => void;
  className?: string;
}

/**
 * Seletor restrito de login corporativo da equipe (/interno/login).
 * Contém exclusivamente as abas Médico e Gestor (sem aba Cidadão).
 */
export function StaffAuthCard({
  initialPerfil = "medico",
  onDoctorAuthenticated,
  onManagerAuthenticated,
  className,
}: StaffAuthCardProps) {
  const [perfil, setPerfil] = useState<PerfilStaffAuth>(initialPerfil);

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      setPerfil((prev) => (prev === "medico" ? "gestor" : "medico"));
    }
  };

  return (
    <div className={cn("w-full max-w-md mx-auto space-y-4", className)}>
      <div className="flex justify-center">
        <div
          role="tablist"
          aria-label="Seleção de perfil interno corporativo"
          onKeyDown={handleTabKeyDown}
          className="inline-flex gap-1 p-1 bg-muted rounded-xl text-xs sm:text-sm w-full"
        >
          <button
            type="button"
            id="tab-medico"
            role="tab"
            aria-selected={perfil === "medico"}
            aria-controls="panel-medico"
            onClick={() => setPerfil("medico")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 min-h-[44px] py-2 px-3 rounded-lg font-semibold transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-center",
              perfil === "medico"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Stethoscope className="size-4 shrink-0 text-primary" aria-hidden="true" />
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
              "flex-1 flex items-center justify-center gap-1.5 min-h-[44px] py-2 px-3 rounded-lg font-semibold transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-center",
              perfil === "gestor"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Building2 className="size-4 shrink-0 text-primary" aria-hidden="true" />
            <span>Gestor</span>
          </button>
        </div>
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

export default StaffAuthCard;
