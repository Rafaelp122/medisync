import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ClinicalPageLayoutProps {
  children: ReactNode;
  subtitle?: string;
  className?: string;
}

/**
 * Layout centrado com cabeçalho institucional para páginas de autenticação,
 * validação pública e estações clínicas/administrativas.
 */
export function ClinicalPageLayout({
  children,
  subtitle = "Pronto Atendimento Virtual & Telemedicina SUS",
  className,
}: ClinicalPageLayoutProps) {
  return (
    <main
      id="main-content"
      className={cn(
        "min-h-screen flex flex-col items-center justify-start p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-background text-foreground",
        className,
      )}
    >
      <header className="mb-4 text-center space-y-1">
        <p className="text-3xl font-extrabold tracking-tight text-primary text-balance">
          MediSync Express
        </p>
        <p className="text-sm text-muted-foreground text-pretty">{subtitle}</p>
      </header>

      {children}
    </main>
  );
}
