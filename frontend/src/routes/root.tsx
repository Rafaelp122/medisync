import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";

export interface RouterContext {
  queryClient: QueryClient;
}

export const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
});

function RootLayout() {
  return (
    <main
      id="main-content"
      className="min-h-screen flex flex-col items-center justify-start p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-background text-foreground"
    >
      <header className="mb-4 text-center space-y-1">
        <h1 className="text-3xl font-extrabold tracking-tight text-primary text-balance">
          MediSync Express
        </h1>
        <p className="text-sm text-muted-foreground text-pretty">
          Pronto Atendimento Virtual & Telemedicina de Urgência
        </p>
      </header>

      <Outlet />
    </main>
  );
}
