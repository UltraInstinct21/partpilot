import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppProviders } from "@/components/app-providers";
import { Toaster } from "@/components/ui/sonner";

import { HomePage } from "@/pages/home-page";
import { SearchPage } from "@/pages/search-page";
import { PartDetailPage } from "@/pages/part-detail-page";
import { ComparePage } from "@/pages/compare-page";
import { BomCheckPage } from "@/pages/bom-check-page";
import { ReviewQueuePage } from "@/pages/review-queue-page";
import { JobsPage } from "@/pages/jobs-page";
import { DashboardPage } from "@/pages/dashboard-page";
import { NotFoundPage } from "@/pages/not-found-page";

export function TestAppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/parts/:partId" element={<PartDetailPage />} />
      <Route path="/parts/:id" element={<PartDetailPage />} />
      <Route path="/compare" element={<ComparePage />} />
      <Route path="/bom" element={<BomCheckPage />} />
      <Route path="/review" element={<ReviewQueuePage />} />
      <Route path="/jobs" element={<JobsPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

/** Render the app with every provider and the router at a given path. */
export function renderApp(initialPath = "/") {
  const user = userEvent.setup();
  const result = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <TestAppRoutes />
        <Toaster />
      </MemoryRouter>
    </AppProviders>,
  );
  return { ...result, user };
}
