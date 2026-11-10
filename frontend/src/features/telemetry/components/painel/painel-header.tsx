import { Building2, LogOut, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface PainelHeaderProps {
  gestorNome: string;
  isFetching: boolean;
  onRefresh: () => void;
  onLogout?: () => void;
}

/**
 * Cabeçalho do Painel de Regulação SUS com indicador de polling e ações.
 */
export function PainelHeader({ gestorNome, isFetching, onRefresh, onLogout }: PainelHeaderProps) {
  return (
    <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card shadow-xs">
      <div className="flex items-center gap-3">
        <div className="size-11 rounded-lg bg-primary/10 flex items-center justify-center text-primary font-bold">
          <Building2 className="size-6" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg sm:text-xl font-extrabold tracking-tight text-foreground">
              Painel de Regulação e Telemetria SUS
            </h1>
            <Badge variant="outline" className="text-[10px] py-0 px-2 gap-1">
              <span className="inline-block size-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span>Polling 5s</span>
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Monitoramento Operacional em Tempo Real • {gestorNome}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 w-full sm:w-auto">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={isFetching}
          className="text-xs h-9 px-3 gap-1.5"
          aria-label="Atualizar telemetria"
        >
          <RefreshCw className={cn("size-3.5", isFetching && "animate-spin text-primary")} />
          <span>{isFetching ? "Atualizando…" : "Atualizar"}</span>
        </Button>

        {onLogout && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onLogout}
            className="text-xs h-9 px-3 gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <LogOut className="size-3.5" />
            <span>Sair</span>
          </Button>
        )}
      </div>
    </header>
  );
}
