import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppProviders } from "@/components/app-providers";
import { Toaster } from "@/components/ui/sonner";
import { AppRoutes } from "@/routes";

/** Render the app with every provider and the router at a given path. */
export function renderApp(initialPath = "/") {
  const user = userEvent.setup();
  const result = render(
    <AppProviders>
      <MemoryRouter initialEntries={[initialPath]}>
        <AppRoutes />
        <Toaster />
      </MemoryRouter>
    </AppProviders>,
  );
  return { ...result, user };
}
