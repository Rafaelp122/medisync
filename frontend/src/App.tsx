import type { QueryClient } from "@tanstack/react-query";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useEffect } from "react";
import { defaultQueryClient } from "@/lib/query-client";
import { sessionTransport } from "@/lib/session-transport";
import { router } from "@/router";

export interface AppProps {
  customRouter?: typeof router;
  customQueryClient?: QueryClient;
}

export function App({ customRouter, customQueryClient }: AppProps = {}) {
  const activeQueryClient = customQueryClient ?? defaultQueryClient;
  const activeRouter = customRouter ?? router;

  useEffect(() => {
    return sessionTransport.subscribeInvalidated(() => {
      activeQueryClient.clear();
    });
  }, [activeQueryClient]);

  return (
    <QueryClientProvider client={activeQueryClient}>
      <RouterProvider router={activeRouter} />
    </QueryClientProvider>
  );
}

export default App;
