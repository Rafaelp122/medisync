import { Link, type LinkProps } from "@tanstack/react-router";
import {
  ArrowRight,
  CalendarClock,
  Clock,
  FileText,
  History,
  Loader2,
  Stethoscope,
} from "lucide-react";
import type { EspecialidadeResponse } from "@/api/generated/types.gen";
import { useEspecialidades } from "@/api/hooks/use-especialidades";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";

type LinkTo = LinkProps["to"];

export interface CitizenHomePageProps {
  session?: StoredPatientSession | null;
}

const FALLBACK_ESPECIALIDADES: EspecialidadeResponse[] = [
  {
    codigo: "PSICOLOGIA",
    nome: "Psicologia",
    descricao: "Acompanhamento psicológico agendado com profissionais da equipe eMulti.",
    duracao_padrao_minutos: 45,
  },
  {
    codigo: "NUTRICAO",
    nome: "Nutrição",
    descricao: "Orientação nutricional e cuidado alimentar multiprofissional agendado.",
    duracao_padrao_minutos: 30,
  },
];

/**
 * Página inicial do Portal do Cidadão (`/home`).
 * Orienta sobre Pronto-Atendimento Digital (casos leves) vs Agenda Multiprofissional (eMulti)
 * e oferece acesso rápido ao histórico, receitas e fila ativa.
 */
export function CitizenHomePage({ session }: CitizenHomePageProps) {
  const activeSession = session ?? getStoredSession();
  const hasActiveAtendimento = Boolean(activeSession?.atendimentoId);
  const { data: especialidades, isLoading: loadingEspecialidades } = useEspecialidades({
    token: activeSession?.token,
  });

  const listaEspecialidades =
    especialidades && especialidades.length > 0 ? especialidades : FALLBACK_ESPECIALIDADES;

  return (
    <CitizenShellLayout session={activeSession}>
      <div className="space-y-6">
        <header className="space-y-1">
          <Badge variant="outline">Portal do Cidadão · SUS Digital</Badge>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Serviços de Saúde Digital
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Escolha o atendimento ideal para sua necessidade clínica atual ou acompanhe seus
            documentos e consultas realizadas.
          </p>
        </header>

        {hasActiveAtendimento && (
          <section
            aria-label="Atendimento ativo na fila"
            className="rounded-xl border border-primary/40 bg-primary/5 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm"
          >
            <div className="flex items-start sm:items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                <Clock className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">
                  Você possui um atendimento ativo na fila virtual
                </p>
                <p className="text-xs text-muted-foreground">
                  Retorne à sala de espera para acompanhar sua posição e atender à chamada médica.
                </p>
              </div>
            </div>
            <Button asChild className="min-h-[44px] w-full sm:w-auto shrink-0">
              <Link to="/fila">
                Ir para Fila Atual
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          </section>
        )}

        {/* Pronto-Atendimento Digital vs eMulti */}
        <section aria-labelledby="servicos-heading" className="space-y-4">
          <h2 id="servicos-heading" className="text-lg font-semibold text-foreground">
            Como podemos ajudar hoje?
          </h2>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Card Pronto-Atendimento Digital */}
            <Card className="flex flex-col justify-between border-border shadow-sm">
              <CardHeader className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Stethoscope className="h-6 w-6" aria-hidden="true" />
                  </div>
                  <Badge variant="nivel4">Atendimento Imediato</Badge>
                </div>
                <CardTitle className="text-lg">Pronto-Atendimento Digital (Casos Leves)</CardTitle>
                <CardDescription>
                  Indicado para febre baixa, dor leve, sintomas respiratórios ou urinários simples,
                  sem sinais de gravidade.
                </CardDescription>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                Você responde à triagem rápida em menos de 1 minuto e entra na fila virtual com
                classificação clínica de risco.
              </CardContent>
              <CardFooter>
                <Button asChild className="w-full min-h-[44px]">
                  <Link to="/triagem">
                    Iniciar Triagem Rápida
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </CardFooter>
            </Card>

            {/* Card Atendimento Multiprofissional eMulti */}
            <Card className="flex flex-col justify-between border-border shadow-sm">
              <CardHeader className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-secondary text-secondary-foreground">
                    <CalendarClock className="h-6 w-6" aria-hidden="true" />
                  </div>
                  <Badge variant="nivel5">Horário Marcado · eMulti</Badge>
                </div>
                <CardTitle className="text-lg">
                  Atendimento Multiprofissional Agendado (eMulti)
                </CardTitle>
                <CardDescription>
                  Agende consultas com hora marcada em Psicologia e Nutrição pela rede municipal
                  SUS.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {loadingEspecialidades ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
                    <span>Carregando especialidades disponíveis…</span>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {listaEspecialidades.map((esp) => (
                      <div
                        key={esp.codigo}
                        className="rounded-lg border border-border bg-muted/30 p-3 flex flex-col justify-between gap-2"
                      >
                        <div>
                          <p className="text-sm font-semibold text-foreground">{esp.nome}</p>
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {esp.descricao}
                          </p>
                          <p className="text-[11px] text-muted-foreground mt-1">
                            Duração: {esp.duracao_padrao_minutos} min
                          </p>
                        </div>
                        <Button asChild variant="outline" size="sm" className="w-full min-h-[44px]">
                          <Link
                            to={"/agendar" as LinkTo}
                            search={{ especialidade: esp.codigo } as never}
                          >
                            Agendar {esp.nome}
                          </Link>
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
              <CardFooter>
                <Button asChild variant="secondary" className="w-full min-h-[44px]">
                  <Link to={"/agendar" as LinkTo}>
                    Ver Agenda Completa
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </CardFooter>
            </Card>
          </div>
        </section>

        {/* Acesso Rápido */}
        <section aria-labelledby="acesso-rapido-heading" className="space-y-3">
          <h2 id="acesso-rapido-heading" className="text-lg font-semibold text-foreground">
            Acesso Rápido
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Link
              to={"/historico" as LinkTo}
              className="flex min-h-[44px] items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 hover:border-primary/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <History className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">Histórico de Consultas</p>
                  <p className="text-xs text-muted-foreground">
                    Consulte atendimentos passados, CID-10 e agendamentos.
                  </p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />
            </Link>

            <Link
              to={"/receitas" as LinkTo}
              className="flex min-h-[44px] items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 hover:border-primary/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FileText className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">Minhas Receitas</p>
                  <p className="text-xs text-muted-foreground">
                    Baixe receitas, atestados e valide códigos ICP-Brasil.
                  </p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </div>
    </CitizenShellLayout>
  );
}

export default CitizenHomePage;
