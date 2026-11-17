import { Link, type LinkProps } from "@tanstack/react-router";
import { ArrowRight, FileCheck2, HeartPulse } from "lucide-react";
import type * as React from "react";
import { Button } from "@/components/ui/button";
import { LandingFooter } from "@/features/landing/components/landing-footer";

export interface PublicLandingLayoutProps {
  children: React.ReactNode;
}

export function PublicLandingLayout({ children }: PublicLandingLayoutProps) {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/95 backdrop-blur-sm">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
          <Link
            to="/"
            className="inline-flex min-h-[44px] items-center gap-2.5 font-bold text-lg tracking-tight text-foreground hover:text-primary transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-md px-1"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <HeartPulse className="h-5 w-5" aria-hidden="true" />
            </span>
            <span>MediSync Express</span>
          </Link>

          <nav
            aria-label="Navegação pública"
            className="flex flex-wrap items-center gap-1 sm:gap-2"
          >
            <a
              href="#arquitetura"
              className="inline-flex min-h-[44px] items-center px-3 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Arquitetura
            </a>
            <a
              href="#sobre"
              className="inline-flex min-h-[44px] items-center px-3 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Sobre
            </a>
            <a
              href="#projetos"
              className="inline-flex min-h-[44px] items-center px-3 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Projetos
            </a>
            <Link
              to={"/validar" as LinkProps["to"]}
              className="inline-flex min-h-[44px] items-center gap-1.5 px-3 rounded-md text-sm font-medium text-foreground hover:text-primary hover:bg-accent transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <FileCheck2 className="h-4 w-4 text-primary" aria-hidden="true" />
              <span>Validar Receita</span>
            </Link>
            <Button asChild size="default" className="ml-1">
              <Link to={"/home" as LinkProps["to"]}>
                <span>Acessar Portal</span>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          </nav>
        </div>
      </header>

      <main id="main-content" className="flex-1">
        {children}
      </main>

      <LandingFooter />
    </div>
  );
}
