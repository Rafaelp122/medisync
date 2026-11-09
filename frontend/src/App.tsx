import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { router } from "@/router";

const defaultQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

export interface AppProps {
  customRouter?: typeof router;
  customQueryClient?: QueryClient;
}

export function App({ customRouter, customQueryClient }: AppProps = {}) {
  const activeQueryClient = customQueryClient ?? defaultQueryClient;
  const activeRouter = customRouter ?? router;

  return (
    <QueryClientProvider client={activeQueryClient}>
      <RouterProvider router={activeRouter} />
    </QueryClientProvider>
  );
}

export default App;
