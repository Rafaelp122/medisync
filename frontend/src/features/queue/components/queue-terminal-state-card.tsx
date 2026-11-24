import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface QueueTerminalStateCardProps {
  status: string;
  className?: string;
  onEncerrarSessao?: () => void;
}

/**
 * Cards terminais da Sala de Espera Virtual: `PACIENTE_AUSENTE`, `CANCELADO_PACIENTE` e `CONCLUIDO`.
 * @see docs/user-stories/US-08-atendimento-chamada-no-show.md
 */
export function QueueTerminalStateCard({
  status,
  className,
  onEncerrarSessao,
}: QueueTerminalStateCardProps) {
  if (status === "PACIENTE_AUSENTE") {
    return (
      <Card
        className={cn(
          "w-full max-w-lg mx-auto shadow-lg text-center space-y-4 border-destructive/30",
          className,
        )}
      >
        <CardHeader>
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive mb-2">
            <span className="text-3xl" aria-hidden="true">
              ⏱️
            </span>
          </div>
          <CardTitle className="text-2xl font-bold text-destructive">
            Chamada Não Atendida
          </CardTitle>
          <CardDescription className="text-sm text-pretty">
            O médico plantonista chamou seu atendimento, mas não houve confirmação dentro da janela
            de 45 segundos (RN02).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-left">
          <p className="text-xs text-muted-foreground leading-relaxed">
            Para garantir agilidade no pronto atendimento e evitar atrasos na fila, sua vaga foi
            liberada para o próximo paciente. Se você ainda precisa de assistência médica, inicie um
            novo acolhimento.
          </p>
          {onEncerrarSessao && (
            <Button type="button" variant="default" className="w-full" onClick={onEncerrarSessao}>
              Iniciar Novo Atendimento
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  if (status === "CONCLUIDO") {
    return (
      <Card className={cn("w-full max-w-lg mx-auto shadow-lg text-center space-y-4", className)}>
        <CardHeader>
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-700 mb-2">
            <span className="text-3xl" aria-hidden="true">
              ✓
            </span>
          </div>
          <CardTitle className="text-xl font-bold text-foreground">Atendimento Concluído</CardTitle>
          <CardDescription className="text-sm">
            Sua teleconsulta foi encerrada. Seus documentos médicos já podem ser consultados no
            portal do cidadão.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {onEncerrarSessao && (
            <Button type="button" variant="default" className="w-full" onClick={onEncerrarSessao}>
              Ir para o Portal
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  if (status === "CANCELADO_PACIENTE" || status === "CANCELADO") {
    return (
      <Card className={cn("w-full max-w-lg mx-auto shadow-lg text-center space-y-4", className)}>
        <CardHeader>
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-muted text-muted-foreground mb-2">
            <span className="text-3xl" aria-hidden="true">
              ✕
            </span>
          </div>
          <CardTitle className="text-xl font-bold text-foreground">Atendimento Cancelado</CardTitle>
          <CardDescription className="text-sm">
            Sua permanência na fila virtual foi encerrada com sucesso (RN06).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {onEncerrarSessao && (
            <Button type="button" variant="outline" className="w-full" onClick={onEncerrarSessao}>
              Voltar ao Início
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  return null;
}
