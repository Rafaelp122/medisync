import { QueryClient } from "@tanstack/react-query";

export const defaultQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});
