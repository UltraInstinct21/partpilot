import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { describeError } from "./client";

/**
 * A single QueryClient for the whole app.
 *
 * Every failed request produces an error toast (sonner). The toast is raised
 * here, in the cache, so that no page can forget it.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        toast.error(describeError(error));
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        toast.error(describeError(error));
      },
    }),
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
