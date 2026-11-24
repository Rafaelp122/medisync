import { LogOut, PhoneCall, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TmaTimerBadge } from "./tma-timer-badge";

export interface DoctorWorkstationHeaderProps {
  medicoNome: string;
  crmUf: string;
  totalPacientesFila: number;
  isCarregandoPainel: boolean;
  isCallingNext: boolean;
  chamadaIniciadaEm?: string | null;
  ttlSegundos?: number | null;
  hasActiveEncounter: boolean;
  onChamarProximo: () => void;
  onLogout?: () => void;
}

function extrairIniciais(nome: string): string {
  const palavras = nome
    .replace(/^(Dr\.?|Dra\.?)\s+/i, "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (palavras.length === 0) return "MD";
  if (palavras.length === 1) return palavras[0].slice(0, 2).toUpperCase();
  return `${palavras[0][0]}${palavras[palavras.length - 1][0]}`.toUpperCase();
}

/**
 * Barra superior da Estação de Trabalho Clínica com iniciais dinâmicas, telemetria e ações.
 */
export function DoctorWorkstationHeader({
  medicoNome,
  crmUf,
  totalPacientesFila,
  isCarregandoPainel,
  isCallingNext,
  chamadaIniciadaEm,
  ttlSegundos,
  hasActiveEncounter,
  onChamarProximo,
  onLogout,
}: DoctorWorkstationHeaderProps) {
  const iniciais = extrairIniciais(medicoNome);

  return (
    <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 rounded-lg border border-border bg-card shadow-xs">
      <div className="flex items-center gap-3">
        <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
          {iniciais}
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-base font-bold text-foreground">{medicoNome}</h1>
            <Badge variant="outline" className="text-[11px] py-0 px-1.5">
              CRM {crmUf}
            </Badge>
            <Badge variant="success" className="text-[10px] py-0 px-1.5 gap-1">
              <span className="inline-block size-1.5 rounded-full bg-acr-green-foreground" />
              Em Plantão
            </Badge>
            <Badge
              variant={totalPacientesFila > 0 ? "outline" : "secondary"}
              className="text-[10px] py-0 px-2 gap-1.5"
              data-testid="badge-pacientes-fila"
            >
              <Users className="size-3 text-muted-foreground" />
              <span>
                {isCarregandoPainel
                  ? "Consultando fila…"
                  : totalPacientesFila === 1
                    ? "1 paciente na fila"
                    : totalPacientesFila > 1
                      ? `${totalPacientesFila} pacientes na fila`
                      : "Fila vazia (0)"}
              </span>
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Estação Clínica Integrada • Telemedicina de Urgência MediSync Express
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 w-full sm:w-auto">
        {hasActiveEncounter && (
          <TmaTimerBadge
            iniciadoEm={chamadaIniciadaEm}
            tmaPlanejadoSegundos={ttlSegundos ?? undefined}
          />
        )}

        <Button
          type="button"
          size="sm"
          onClick={onChamarProximo}
          disabled={isCallingNext}
          className="text-xs font-semibold h-9 px-4 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
        >
          <PhoneCall className="size-4" />
          <span>{isCallingNext ? "Adquirindo da fila…" : "Chamar Próximo Paciente"}</span>
        </Button>

        {onLogout && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onLogout}
            className="text-xs font-medium h-9 px-3 gap-1.5 text-muted-foreground hover:text-foreground border-border"
          >
            <LogOut className="size-3.5" />
            <span>Sair do Plantão</span>
          </Button>
        )}
      </div>
    </header>
  );
}
