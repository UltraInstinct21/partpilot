import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toast";
import { createQueryClient } from "@/api/query-client";
import { CompareProvider } from "@/lib/compare-store";
import { ReviewQueueProvider } from "@/lib/review-queue-store";

/**
 * Global application providers:
 * - QueryClientProvider for TanStack Query
 * - TooltipProvider for parameter condition hints and discrepancy popovers
 * - CompareProvider for managing the persistent compare tray
 * - ReviewQueueProvider for managing components queued for final review & export
 * - Sonner Toaster for accessible notifications
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={150}>
        <CompareProvider>
          <ReviewQueueProvider>
            {children}
            <Toaster progressBar={true} />
          </ReviewQueueProvider>
        </CompareProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
