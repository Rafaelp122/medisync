import { type ErrorComponentProps, Link } from "@tanstack/react-router";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { extractProblemDetail } from "@/api/errors";
import { Button } from "@/components/ui/button";

export function RoutePendingFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-[240px] w-full items-center justify-center gap-2 text-sm text-muted-foreground"
    >
      <Loader2 className="size-4 animate-spin text-primary" aria-hidden="true" />
      <span>Carregando página…</span>
    </div>
  );
}

export function RouteErrorFallback({ error, reset }: ErrorComponentProps) {
  const detail = extractProblemDetail(
    error,
    "Ocorreu uma falha inesperada ao carregar esta página.",
  );

  return (
    <div
      role="alert"
      className="mx-auto my-12 max-w-md rounded-xl border border-destructive/30 bg-card p-6 text-card-foreground shadow-sm space-y-4"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="size-5 shrink-0 text-destructive mt-0.5" aria-hidden="true" />
        <div className="space-y-1">
          <h1 className="text-base font-bold text-foreground">Erro ao carregar a rota</h1>
          <p className="text-xs text-muted-foreground">{detail}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => reset()} className="min-h-[44px] gap-1.5">
          <RefreshCw className="size-4" aria-hidden="true" />
          <span>Tentar novamente</span>
        </Button>
        <Button asChild type="button" variant="outline" size="sm" className="min-h-[44px]">
          <Link to="/">Voltar ao início</Link>
        </Button>
      </div>
    </div>
  );
}
