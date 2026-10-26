import { BrowserRouter, useLocation } from "react-router-dom";
import { AppProviders } from "@/components/app-providers";
import { AppNav } from "@/components/app-nav";
import { CompareTray } from "@/components/domain/compare-tray";
import { ErrorBoundary } from "@/components/error-boundary";
import { AppRoutes } from "@/routes";
import { cn } from "@/lib/utils";

function AppContent() {
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <div className="flex min-h-screen flex-col bg-black text-white relative">
      <AppNav />
      <main
        id="main-content"
        role="main"
        className={cn(
          "w-full flex-1",
          isHome ? "pt-0" : "w-full max-w-7xl mx-auto px-4 sm:px-8 lg:px-12 pt-28 pb-16",
        )}
      >
        <AppRoutes />
      </main>
      <CompareTray />
    </div>
  );
}

/** The application shell. */
export default function App() {
  return (
    <ErrorBoundary>
      <AppProviders>
        <BrowserRouter>
          <AppContent />
        </BrowserRouter>
      </AppProviders>
    </ErrorBoundary>
  );
}
