import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "@/components/app-providers";
import { AppNav } from "@/components/app-nav";
import { Toaster } from "@/components/ui/sonner";
import { AppRoutes } from "@/routes";

/** The application shell. */
export default function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <div className="flex min-h-screen flex-col bg-background">
          <AppNav />
          <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6">
            <AppRoutes />
          </main>
          <Toaster />
        </div>
      </BrowserRouter>
    </AppProviders>
  );
}
