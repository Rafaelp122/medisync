import { Link } from "@tanstack/react-router";
import { ArrowRight, Clock, HeartPulse, Smartphone, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { getStoredSession } from "@/lib/session-storage";

export function HomeLanding() {
  const session = getStoredSession();
  const hasActiveEncounter = Boolean(session?.atendimentoId);

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6 py-4">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
          <HeartPulse className="h-3.5 w-3.5" />
          <span>SUS · Pronto Atendimento Digital</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
          Pronto Atendimento Virtual
        </h1>
        <p className="text-sm sm:text-base text-muted-foreground max-w-lg mx-auto">
          Acolhimento clínico imediato, triagem de urgência e teleconsulta médica sem filas
          presenciais.
        </p>
      </div>

      {hasActiveEncounter && (
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-3 text-left">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Clock className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">
                Você possui um atendimento ativo
              </p>
              <p className="text-xs text-muted-foreground">
                Retorne à sala de espera virtual para acompanhar sua posição na fila.
              </p>
            </div>
          </div>
          <Button asChild size="sm" className="w-full sm:w-auto shrink-0">
            <Link to="/fila">Ir para a Fila</Link>
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card className="flex flex-col justify-between hover:border-primary/50 transition-colors shadow-sm">
          <CardHeader>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary mb-2">
              <Stethoscope className="h-6 w-6" />
            </div>
            <CardTitle className="text-lg sm:text-xl">Novo Atendimento</CardTitle>
            <CardDescription className="text-xs sm:text-sm">
              Inicie sua triagem clínica de urgência com avaliação de sintomas, escala de dor e
              consentimento digital.
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Button asChild className="w-full">
              <Link to="/triagem">
                Iniciar Triagem
                <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </Button>
          </CardFooter>
        </Card>

        <Card className="flex flex-col justify-between hover:border-primary/50 transition-colors shadow-sm">
          <CardHeader>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-secondary text-secondary-foreground mb-2">
              <Smartphone className="h-6 w-6" />
            </div>
            <CardTitle className="text-lg sm:text-xl">Já Tenho Atendimento</CardTitle>
            <CardDescription className="text-xs sm:text-sm">
              Acompanhe sua chamada ou recupere sua sessão usando seu número de telefone celular via
              código SMS.
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Button asChild variant="outline" className="w-full">
              <Link to="/otp">
                Acompanhar por SMS
                <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </Button>
          </CardFooter>
        </Card>
      </div>

      <footer className="pt-6 pb-2 text-center text-xs text-muted-foreground border-t border-border/40">
        <p>
          Atendimento oficial do Sistema Único de Saúde ·{" "}
          <Link
            to="/login"
            className="text-muted-foreground hover:text-foreground hover:underline transition-colors"
          >
            Área do Profissional
          </Link>
        </p>
      </footer>
    </div>
  );
}
