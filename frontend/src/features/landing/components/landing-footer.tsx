import { Link, type LinkProps } from "@tanstack/react-router";
import { FileCheck2, HeartPulse, Scale } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function LandingFooter() {
  return (
    <footer className="border-t border-border bg-muted/40 text-foreground">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 space-y-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="space-y-3">
            <div className="flex items-center gap-2 font-bold text-base text-foreground">
              <HeartPulse className="h-5 w-5 text-primary" aria-hidden="true" />
              <span>MediSync Express</span>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed text-pretty">
              Infraestrutura aberta de pronto-atendimento virtual para casos leves e atenção
              multiprofissional (eMulti / SUS).
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Badge variant="secondary" className="gap-1.5">
                <Scale className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Licença MIT / Apache 2.0</span>
              </Badge>
            </div>
          </div>

          <div className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground">
              Navegação Pública
            </h2>
            <ul className="space-y-1 text-sm">
              <li>
                <Link
                  to={"/home" as LinkProps["to"]}
                  className="inline-flex min-h-[44px] items-center text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
                >
                  Acessar Portal do Cidadão
                </Link>
              </li>
              <li>
                <Link
                  to={"/cadastro" as LinkProps["to"]}
                  className="inline-flex min-h-[44px] items-center text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
                >
                  Criar Conta
                </Link>
              </li>
              <li>
                <Link
                  to={"/validar" as LinkProps["to"]}
                  className="inline-flex min-h-[44px] items-center gap-1.5 text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
                >
                  <FileCheck2 className="h-4 w-4 text-primary" aria-hidden="true" />
                  <span>Validar Receita</span>
                </Link>
              </li>
            </ul>
          </div>

          <div className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground">
              Seções Técnicas
            </h2>
            <ul className="space-y-1 text-sm">
              <li>
                <a
                  href="#arquitetura"
                  className="inline-flex min-h-[44px] items-center text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
                >
                  Arquitetura & Engenharia
                </a>
              </li>
              <li>
                <a
                  href="#sobre"
                  className="inline-flex min-h-[44px] items-center text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
                >
                  Sobre Mim
                </a>
              </li>
              <li>
                <a
                  href="#projetos"
                  className="inline-flex min-h-[44px] items-center text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1"
                >
                  Outros Projetos
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4 text-xs text-muted-foreground leading-relaxed space-y-1.5">
          <p className="font-semibold text-foreground">
            Aviso Institucional & Isenção de Escopo (Portfólio Técnico)
          </p>
          <p>
            O MediSync Express é um projeto conceitual de engenharia de software e arquitetura
            avançada desenvolvido para fins de portfólio técnico, estruturado sobre marcos
            regulatórios reais da saúde brasileira (Resoluções CFM nº 2.314/2022 e 1.821/2007, Art.
            11 da LGPD, Portaria SVS/MS nº 344/98 e RDC ANVISA nº 20/2011).
          </p>
          <p>
            Não constitui dispositivo médico homologado pela ANVISA nem deve ser utilizado em
            ambiente de assistência clínica real sem prévia validação médica, comitê de ética e
            auditoria de segurança institucional.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-between gap-2 border-t border-border/60 pt-4 text-xs text-muted-foreground">
          <p>MediSync Express · Software Livre sob licença dupla MIT / Apache 2.0.</p>
          <p>Conformidade assistencial projetada para WCAG 2.1 AA.</p>
        </div>
      </div>
    </footer>
  );
}
