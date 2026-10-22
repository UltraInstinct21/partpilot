import { ThemeProvider } from "next-themes";
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { createQueryClient } from "@/api/query-client";

/**
 * All the providers the app needs.
 *
 * - `QueryClientProvider` for TanStack Query (the data layer).
 * - `ThemeProvider` from next-themes, required by the shadcn `sonner`
 *   component because it calls `useTheme`.
 * - `TooltipProvider`, required by the shadcn tooltip.
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
