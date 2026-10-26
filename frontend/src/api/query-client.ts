import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "@/components/ui/toast";
import { ApiError, describeError } from "./client";

/**
 * Single QueryClient configuration for PartPilot:
 * - Parts: 5 minutes staleTime
 * - No retries on 4xx errors
 * - 2 retries with exponential backoff on network errors and 5xx
 * - Normalized error toast notifications
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
        // In tests, no retries so error assertions don't time out
        // In production, no retry on 4xx; two retries with backoff on network errors and 5xx
        retry: import.meta.env.MODE === "test" ? false : (failureCount, error) => {
          if (error instanceof ApiError) {
            if (error.status >= 400 && error.status < 500) {
              return false;
            }
          }
          return failureCount < 2;
        },
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
        // Sensible staleTime: parts 5 minutes (300,000ms)
        staleTime: 5 * 60 * 1000,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
