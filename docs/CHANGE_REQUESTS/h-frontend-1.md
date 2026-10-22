# Change request H-frontend-1

**From:** agent H-frontend (WP7, frontend)
**Date:** 2026-10-22
**Kind:** informational - changes inside my own write access, no action required

## What I changed outside the files I created

`frontend/src/test/setup.ts` is inside my write access (`frontend/src/**`), but
it is shared test infrastructure that the orchestrator wrote, so the change is
listed here for the record.

### 1. Stubs for `matchMedia` and `ResizeObserver`

jsdom implements neither. `next-themes` (the `ThemeProvider` that the shadcn
`sonner` component needs) calls `window.matchMedia` and `recharts` uses
`ResizeObserver`. Without the stubs every test that renders the app fails with
`window.matchMedia is not a function`.

### 2. The `File` class of Node instead of the one of jsdom

```ts
import { File as NodeFile } from "node:buffer";
globalThis.File = NodeFile as unknown as typeof globalThis.File;
```

The multipart parser of Node checks the tag of the `File` objects it creates.
With the `File` of jsdom the check fails and every multipart request answers
`500` with

```
assert(typeof value === "string" && webidl.is.USVString(value) || webidl.is.File(value))
```

The frozen mock (`frontend/src/mocks/handlers.ts`) parses the upload with
`request.formData()`, so the BOM check could not work without this change.

`node:buffer` is not part of the `types` array of `tsconfig.app.json`, so a
small declaration was added in `frontend/src/test/node-buffer.d.ts` (also
inside my write access). `tsconfig*.json` was **not** modified.

## What I did NOT touch

* `frontend/src/api/types.ts` (generated)
* `frontend/src/mocks/**` (frozen mock)
* `frontend/package.json`, `package-lock.json`
* `frontend/vite.config.ts`, `frontend/tsconfig*.json`, `frontend/components.json`
* `contracts/**`

## New dependency?

No. The `Checkbox` of `src/components/ui/checkbox.tsx` uses the `radix-ui`
package that is already installed (`@radix-ui/react-checkbox` is one of its
dependencies). The shadcn CLI was therefore not needed for that component.
