import { QueryClient } from "@tanstack/react-query";
import { sessionTransport } from "./session-transport";

export const defaultQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

sessionTransport.subscribeInvalidated(() => {
  defaultQueryClient.clear();
});
