import { Link, type LinkProps } from "@tanstack/react-router";
import { ArrowRight, CheckCircle2, FileCheck2, ShieldCheck, UserPlus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CARE_PIPELINE_STEPS = [
  {
    step: "01",
    title: "Acolhimento Ágil",
    detail:
      "Triagem clínica estruturada com consentimento digital (TCLE Hash) e rota segura SAMU 192.",
  },
  {
    step: "02",
    title: "Fila Atômica & eMulti",
    detail:
      "Ordenação por gravidade clínica e tempo de espera no Valkey, com suporte a agenda multiprofissional.",
  },
  {
    step: "03",
    title: "Qualificação SUS Assíncrona",
    detail:
      "Integração cadastral (CPF / CNS / CADSUS) sem bloquear o ingresso imediato do cidadão na fila.",
  },
  {
    step: "04",
    title: "Teleconsulta WebRTC",
    detail:
      "Atendimento em sala LiveKit SFU com prontuário SOAP e prescrição digital assinada em ICP-Brasil.",
  },
] as const;

export function HeroSection() {
  return (
    <section
      aria-labelledby="hero-heading"
      className="border-b border-border/70 bg-gradient-to-b from-secondary/40 via-background to-background"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-12 sm:py-16 lg:py-20 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
        <div className="lg:col-span-7 space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="px-3 py-1 text-xs">
              Open Source · MIT / Apache 2.0
            </Badge>
            <Badge variant="outline" className="px-3 py-1 text-xs">
              Pronto-Atendimento Digital · eMulti / SUS
            </Badge>
          </div>

          <h1
            id="hero-heading"
            className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-foreground text-balance leading-[1.12]"
          >
            Pronto-Atendimento Digital para Casos Leves & Atenção Multiprofissional
          </h1>

          <p className="text-base sm:text-lg text-muted-foreground leading-relaxed text-pretty max-w-2xl">
            UPAs e prontos-socorros físicos do SUS sofrem com superlotação causada por demandas de
            baixa complexidade (fichas verdes e azuis). O{" "}
            <strong className="font-semibold text-foreground">MediSync Express</strong> é uma
            infraestrutura aberta de teleatendimento sob demanda espontânea e atenção
            multiprofissional (eMulti), projetada para triar, enfileirar e atender com segurança
            clínica e rigor regulatório brasileiro.
          </p>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-1">
            <Button asChild size="lg">
              <Link to={"/home" as LinkProps["to"]}>
                <span>Acessar Portal do Cidadão</span>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>

            <Button asChild variant="outline" size="lg">
              <Link to={"/cadastro" as LinkProps["to"]}>
                <UserPlus className="h-4 w-4" aria-hidden="true" />
                <span>Criar Conta</span>
              </Link>
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-1 text-sm text-muted-foreground">
            <Link
              to={"/entrar" as LinkProps["to"]}
              className="inline-flex min-h-[44px] items-center gap-1.5 font-medium text-primary hover:underline underline-offset-4 transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
            >
              <span>Já possui cadastro? Entrar</span>
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>

            <Link
              to={"/validar" as LinkProps["to"]}
              className="inline-flex min-h-[44px] items-center gap-1.5 font-medium text-foreground hover:text-primary hover:underline underline-offset-4 transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
            >
              <FileCheck2 className="h-4 w-4 text-primary" aria-hidden="true" />
              <span>Validar autenticidade de receita</span>
            </Link>
          </div>
        </div>

        <div className="lg:col-span-5">
          <Card className="border-border bg-card shadow-md">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between gap-2">
                <Badge variant="nivel5">Esteira Assistencial</Badge>
                <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
                  <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
                  <span>CFM nº 2.314/2022 · LGPD</span>
                </span>
              </div>
              <CardTitle className="text-lg pt-2">
                Fluxo contínuo do acolhimento à prescrição assinada
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <ol className="space-y-3">
                {CARE_PIPELINE_STEPS.map((item) => (
                  <li
                    key={item.step}
                    className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/30 p-3"
                  >
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-bold text-primary">
                      {item.step}
                    </span>
                    <div className="space-y-0.5">
                      <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                        <span>{item.title}</span>
                        <CheckCircle2
                          className="h-3.5 w-3.5 text-primary shrink-0"
                          aria-hidden="true"
                        />
                      </p>
                      <p className="text-xs text-muted-foreground leading-relaxed">{item.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
