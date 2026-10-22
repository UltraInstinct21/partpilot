import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

/**
 * The browser mock (MSW) is started only when `VITE_USE_MOCKS=true`.
 * The mock serves exactly the same `/api/...` paths as the real backend, so
 * the frontend code is identical in both modes (NFR-07).
 */
async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCKS === "true") {
    const { worker } = await import("@/mocks/browser");
    await worker.start();
  }

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
