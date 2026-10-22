import { Route, Routes } from "react-router-dom";
import { SearchPage } from "@/pages/search-page";
import { PartDetailPage } from "@/pages/part-detail-page";
import { ComparePage } from "@/pages/compare-page";
import { BomCheckPage } from "@/pages/bom-check-page";
import { ReviewQueuePage } from "@/pages/review-queue-page";
import { DashboardPage } from "@/pages/dashboard-page";

/** The route map of the application. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<SearchPage />} />
      <Route path="/parts/:partId" element={<PartDetailPage />} />
      <Route path="/compare" element={<ComparePage />} />
      <Route path="/bom" element={<BomCheckPage />} />
      <Route path="/review" element={<ReviewQueuePage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="*" element={<SearchPage />} />
    </Routes>
  );
}
