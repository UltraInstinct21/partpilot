/**
 * MSW worker for the browser. Start it in `main.tsx` when the app runs in
 * mock mode (`VITE_USE_MOCKS=true`). The default dev mode talks to the real
 * backend through the Vite proxy.
 */
import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
