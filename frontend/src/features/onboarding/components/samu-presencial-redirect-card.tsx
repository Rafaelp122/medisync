import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export interface SamuPresencialRedirectCardProps {
  orientacoes: string | null;
  onReiniciar: () => void;
}

/**
 * Card terminal de redirecionamento presencial quando a triagem detecta risco clínico nível 1 (SAMU 192).
 * @see docs/user-stories/US-06-deterioracao-clinica-escape-samu.md
 */
export function SamuPresencialRedirectCard({
  orientacoes,
  onReiniciar,
}: SamuPresencialRedirectCardProps) {
  return (
    <Card className="w-full max-w-xl mx-auto shadow-md border-destructive/50">
      <CardHeader className="text-center space-y-2">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <span className="text-3xl" aria-hidden="true">
            🚑
          </span>
        </div>
        <CardTitle className="text-xl font-bold text-destructive">
          Atendimento Presencial de Urgência Recomendado
        </CardTitle>
        <CardDescription className="text-base text-foreground/90 font-medium leading-relaxed">
          Seus sintomas ou queixas exigem avaliação clínica física imediata.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-left">
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-foreground space-y-2">
          <p className="font-semibold text-destructive">Instruções Importantes:</p>
          <p className="leading-relaxed">
            {orientacoes ||
              "Dirija-se imediatamente à Unidade de Pronto Atendimento (UPA) ou Pronto-Socorro hospitalar mais próximo da sua região. Se houver desmaio, dor forte no peito ou piora súbita, ligue 192."}
          </p>
        </div>

        <Button asChild variant="destructive" size="lg" className="w-full font-bold shadow-md">
          <a href="tel:192" className="flex items-center justify-center gap-2">
            <span aria-hidden="true">📞</span>
            Ligar para o SAMU 192
          </a>
        </Button>

        <Button
          type="button"
          variant="outline"
          className="w-full text-xs text-muted-foreground"
          onClick={onReiniciar}
        >
          🔄 Reiniciar Acolhimento do Início
        </Button>
      </CardContent>
    </Card>
  );
}
