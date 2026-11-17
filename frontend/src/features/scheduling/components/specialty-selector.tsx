import { AlertCircle, Brain, Clock, Loader2, Utensils } from "lucide-react";
import { getHumanizedErrorMessage, type ProblemDetailsError } from "@/api/errors";
import type { EspecialidadeResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface SpecialtySelectorProps {
  especialidades: EspecialidadeResponse[];
  selectedCodigo: string;
  onSelect: (codigo: string) => void;
  isLoading?: boolean;
  error?: ProblemDetailsError | null;
}

function EspecialidadeIcon({ codigo }: { codigo: string }) {
  if (codigo.toUpperCase() === "NUTRICAO") {
    return <Utensils className="size-5 text-primary" aria-hidden="true" />;
  }
  return <Brain className="size-5 text-primary" aria-hidden="true" />;
}

/**
 * Seletor acessível de especialidades programadas (eMulti: Psicologia e Nutrição).
 * Exibe descrição clínica e duração padrão da consulta com alvos de toque >= 44px.
 */
export function SpecialtySelector({
  especialidades,
  selectedCodigo,
  onSelect,
  isLoading = false,
  error = null,
}: SpecialtySelectorProps) {
  const erroHumanizado = error ? getHumanizedErrorMessage(error) : null;

  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">1. Escolha a Especialidade</CardTitle>
        <CardDescription>
          Selecione a área multiprofissional (eMulti) para consultar os horários disponíveis.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {erroHumanizado && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>{erroHumanizado.title}</AlertTitle>
            <AlertDescription>{erroHumanizado.detail}</AlertDescription>
          </Alert>
        )}

        {isLoading ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 py-4 text-sm text-muted-foreground"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span>Carregando especialidades disponíveis…</span>
          </div>
        ) : especialidades.length === 0 && !error ? (
          <p className="text-sm text-muted-foreground py-2">
            Nenhuma especialidade programada disponível no momento.
          </p>
        ) : (
          <fieldset
            aria-label="Especialidades multiprofissionais disponíveis"
            className="grid grid-cols-1 sm:grid-cols-2 gap-3 border-0 p-0 m-0"
          >
            {especialidades.map((esp) => {
              const isSelected = esp.codigo.toUpperCase() === selectedCodigo.toUpperCase();
              return (
                <button
                  key={esp.codigo}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onSelect(esp.codigo)}
                  className={cn(
                    "min-h-[44px] w-full text-left rounded-xl border p-4 transition-[border-color,background-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    isSelected
                      ? "border-primary bg-primary/5 ring-2 ring-primary/30 shadow-xs"
                      : "border-border bg-card hover:border-primary/50 hover:bg-muted/30",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                        <EspecialidadeIcon codigo={esp.codigo} />
                      </div>
                      <div>
                        <span className="block text-base font-semibold text-foreground">
                          {esp.nome}
                        </span>
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                          <Clock className="size-3.5" aria-hidden="true" />
                          <span>Duração padrão: {esp.duracao_padrao_minutos} min</span>
                        </span>
                      </div>
                    </div>
                    {isSelected && (
                      <Badge variant="default" className="shrink-0">
                        Selecionada
                      </Badge>
                    )}
                  </div>
                  <p className="mt-2.5 text-sm text-muted-foreground leading-relaxed">
                    {esp.descricao}
                  </p>
                </button>
              );
            })}
          </fieldset>
        )}
      </CardContent>
    </Card>
  );
}
