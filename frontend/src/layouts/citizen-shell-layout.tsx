import { useQueryClient } from "@tanstack/react-query";
import { Link, type LinkProps, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  CalendarClock,
  Clock,
  FileText,
  HeartPulse,
  History,
  Home,
  LogOut,
  UserRound,
} from "lucide-react";
import { createContext, type ReactNode, use } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { cn } from "@/lib/utils";

const CitizenShellContext = createContext(false);

type LinkTo = LinkProps["to"];

interface CitizenNavItem {
  to: string;
  label: string;
  mobileLabel: string;
  icon: typeof Home;
  highlighted?: boolean;
}

export interface CitizenShellLayoutProps {
  children?: ReactNode;
  session?: StoredPatientSession | null;
  onLogout?: () => void;
}

/**
 * Shell responsivo do Portal do Cidadão (Sidebar desktop + Barra inferior mobile).
 * Garante navegação acessível (WCAG 2.1 AA, min-h-[44px], safe-area-inset-bottom)
 * sem expor rotas internas corporativas.
 */
export function CitizenShellLayout({ children, session, onLogout }: CitizenShellLayoutProps) {
  const isInsideShell = use(CitizenShellContext);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });

  if (isInsideShell) {
    return <>{children ?? <Outlet />}</>;
  }

  const activeSession = session ?? getStoredSession();
  const hasActiveAtendimento = Boolean(activeSession?.atendimentoId);

  const navItems: CitizenNavItem[] = [
    { to: "/home", label: "Início / Serviços", mobileLabel: "Início", icon: Home },
    { to: "/agendar", label: "Agendar Consulta", mobileLabel: "Agendar", icon: CalendarClock },
    ...(hasActiveAtendimento
      ? [
          {
            to: "/fila",
            label: "Fila Atual",
            mobileLabel: "Fila",
            icon: Clock,
            highlighted: true,
          },
        ]
      : []),
    { to: "/historico", label: "Histórico", mobileLabel: "Histórico", icon: History },
    { to: "/receitas", label: "Receitas e Documentos", mobileLabel: "Receitas", icon: FileText },
    { to: "/perfil", label: "Perfil e Dependentes", mobileLabel: "Perfil", icon: UserRound },
  ];

  const handleLogout = () => {
    sessionTransport.clearSession("patient");
    queryClient.clear();
    if (onLogout) {
      onLogout();
      return;
    }
    navigate({ to: "/" });
  };

  return (
    <CitizenShellContext value={true}>
      <div className="min-h-screen w-full flex flex-col md:flex-row bg-background text-foreground">
        {/* Sidebar Desktop */}
        <aside className="hidden md:flex md:w-64 md:shrink-0 md:flex-col border-r border-border bg-card">
          <div className="p-4 border-b border-border">
            <Link
              to={"/home" as LinkTo}
              className="flex min-h-[44px] items-center gap-2.5 rounded-md px-1 font-bold text-base tracking-tight text-foreground hover:text-primary transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                <HeartPulse className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="leading-tight">
                MediSync
                <span className="block text-[11px] font-medium text-muted-foreground">
                  Portal do Cidadão
                </span>
              </span>
            </Link>
          </div>

          <nav
            aria-label="Navegação do Portal do Cidadão"
            className="flex-1 p-3 space-y-1.5 overflow-y-auto"
          >
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to as LinkTo}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex min-h-[44px] items-center justify-between gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    isActive
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : item.highlighted
                        ? "bg-primary/10 text-primary border border-primary/30 hover:bg-primary/15"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  <span className="flex items-center gap-2.5 min-w-0">
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{item.label}</span>
                  </span>
                  {item.highlighted && (
                    <Badge variant={isActive ? "secondary" : "nivel5"} className="shrink-0">
                      Ativa
                    </Badge>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="p-3 border-t border-border">
            <Button
              type="button"
              variant="outline"
              onClick={handleLogout}
              className="w-full min-h-[44px] justify-start gap-2.5 text-foreground"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              <span>Sair</span>
            </Button>
          </div>
        </aside>

        {/* Área Principal + Header Mobile */}
        <div className="flex-1 min-w-0 flex flex-col">
          <header className="md:hidden sticky top-0 z-30 flex items-center justify-between gap-2 border-b border-border bg-background/95 backdrop-blur-sm px-4 py-2">
            <Link
              to={"/home" as LinkTo}
              className="flex min-h-[44px] items-center gap-2 font-bold text-sm text-foreground"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <HeartPulse className="h-4 w-4" aria-hidden="true" />
              </span>
              <span>MediSync · Cidadão</span>
            </Link>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="min-h-[44px] gap-1.5 px-3 text-xs font-medium"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              <span>Sair</span>
            </Button>
          </header>

          <main
            id="main-content"
            className="flex-1 min-w-0 w-full max-w-5xl mx-auto px-4 py-5 sm:px-6 pb-[max(5.5rem,calc(env(safe-area-inset-bottom)+4.75rem))] md:pb-8"
          >
            {children ?? <Outlet />}
          </main>
        </div>

        {/* Navegação Inferior Mobile */}
        <nav
          aria-label="Navegação rápida mobile"
          className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-border bg-background/95 backdrop-blur-sm pb-[env(safe-area-inset-bottom)]"
        >
          <ul className="flex items-stretch justify-around px-1 py-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.to;
              return (
                <li key={item.to} className="flex-1 min-w-0">
                  <Link
                    to={item.to as LinkTo}
                    aria-label={item.label}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex min-h-[44px] flex-col items-center justify-center gap-0.5 rounded-md px-1 py-1.5 text-[11px] font-medium transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isActive
                        ? "text-primary font-semibold"
                        : item.highlighted
                          ? "text-primary bg-primary/10"
                          : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="truncate max-w-full">{item.mobileLabel}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </CitizenShellContext>
  );
}

export default CitizenShellLayout;
