import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { ProgressLoadingState } from "@/components/motion-grid-loader";

// Lazy-load every route to minimize initial JavaScript bundle (target < 250 KB gzip)
const HomePage = lazy(() => import("@/pages/home-page").then((m) => ({ default: m.HomePage })));
const SearchPage = lazy(() => import("@/pages/search-page").then((m) => ({ default: m.SearchPage })));
const PartDetailPage = lazy(() => import("@/pages/part-detail-page").then((m) => ({ default: m.PartDetailPage })));
const ComparePage = lazy(() => import("@/pages/compare-page").then((m) => ({ default: m.ComparePage })));
const BomCheckPage = lazy(() => import("@/pages/bom-check-page").then((m) => ({ default: m.BomCheckPage })));
const ReviewQueuePage = lazy(() => import("@/pages/review-queue-page").then((m) => ({ default: m.ReviewQueuePage })));
const JobsPage = lazy(() => import("@/pages/jobs-page").then((m) => ({ default: m.JobsPage })));
const DashboardPage = lazy(() => import("@/pages/dashboard-page").then((m) => ({ default: m.DashboardPage })));
const NotFoundPage = lazy(() => import("@/pages/not-found-page").then((m) => ({ default: m.NotFoundPage })));

function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center p-6">
      <ProgressLoadingState
        title="Loading module…"
        description="Initializing bundle chunk and caching routes."
        size="md"
        className="w-full max-w-md shadow-2xl"
      />
    </div>
  );
}

/** The data router map of PartPilot with code-split lazy routes. */
export function AppRoutes() {
  return (
    <Suspense fallback={<RouteFallback />}>
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
    </Suspense>
  );
}
