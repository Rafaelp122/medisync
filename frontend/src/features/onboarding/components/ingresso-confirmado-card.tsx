import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { StoredPatientSession } from "@/lib/session-storage";
import { cn } from "@/lib/utils";

export interface IngressoConfirmadoCardProps {
  session: StoredPatientSession;
  onEncerrarSessao?: () => void;
  className?: string;
}

/**
 * Card canônico unificado de sessão ativa do paciente e acompanhamento da fila virtual.
 * Regras: US-01, US-02, ADR-011 e conformidade de acessibilidade WCAG 2.1 AA.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export function IngressoConfirmadoCard({
  session,
  onEncerrarSessao,
  className,
}: IngressoConfirmadoCardProps) {
  return (
    <Card className={cn("w-full max-w-md mx-auto shadow-lg text-center space-y-4", className)}>
      <CardHeader>
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-2">
          <span className="text-3xl font-bold" aria-hidden="true">
            ✓
          </span>
        </div>
        <CardTitle className="text-2xl font-bold text-primary text-balance">
          {session.atendimentoId ? "Ingresso Confirmado!" : "Acesso Autorizado"}
        </CardTitle>
        <CardDescription className="text-pretty">
          {session.atendimentoId
            ? "Você já está posicionado na fila virtual de espera do Pronto Atendimento."
            : "Sua sessão de paciente está autenticada na plataforma."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-left">
        <div className="p-4 bg-muted/50 rounded-lg text-xs font-mono space-y-1.5 border">
          {session.atendimentoId ? (
            <>
              <p>
                <strong>Atendimento ID:</strong> {session.atendimentoId}
              </p>
              {session.prioridadeClinica !== undefined && (
                <p>
                  <strong>Prioridade Clínica:</strong> Nível {session.prioridadeClinica} (ACR)
                </p>
              )}
              <p>
                <strong>Status:</strong> {session.status ?? "TRIADO_AGUARDANDO_ELEGIBILIDADE"}
              </p>
            </>
          ) : (
            <>
              <p>
                <strong>Paciente ID:</strong> {session.pacienteId}
              </p>
              <p>
                <strong>Papel:</strong> {session.role}
              </p>
              <p>
                <strong>Status:</strong> Autenticado na Plataforma
              </p>
            </>
          )}
        </div>

        <p className="text-sm text-muted-foreground leading-relaxed text-pretty">
          {session.atendimentoId
            ? "Nossa equipe médica está ciente e sua chamada será iniciada em instantes. Mantenha esta tela aberta para receber a notificação de chamada com áudio e vídeo."
            : "Você não possui atendimento em andamento no momento. Se precisar de assistência médica, encerre esta sessão e inicie um novo atendimento."}
        </p>

        {onEncerrarSessao && (
          <Button
            type="button"
            variant="outline"
            className="w-full mt-4"
            onClick={onEncerrarSessao}
          >
            Encerrar Sessão / Novo Atendimento
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
