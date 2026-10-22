/**
 * The `node:buffer` module is not part of the TypeScript configuration of the
 * app (the `types` array of `tsconfig.app.json` only loads the test types).
 * Only the `File` class of Node is needed, to replace the one of jsdom in the
 * test setup.
 */
declare module "node:buffer" {
  export const File: typeof globalThis.File;
}
