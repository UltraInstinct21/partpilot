import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { File as NodeFile } from "node:buffer";
import { server } from "@/mocks/server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/**
 * jsdom replaces the global `File` with its own class. The multipart parser
 * of Node checks the tag of the file objects it creates, so the upload of the
 * BOM CSV would fail with the jsdom class. The `File` of Node is used
 * instead.
 */
globalThis.File = NodeFile as unknown as typeof globalThis.File;

if (typeof (globalThis as any).SVGGeometryElement === "undefined") {
  class MockSVGGeometryElement {}
  (globalThis as any).SVGGeometryElement = MockSVGGeometryElement;
  if (typeof window !== "undefined") {
    (window as any).SVGGeometryElement = MockSVGGeometryElement;
  }
}

if (typeof Element !== "undefined" && !Element.prototype.animate) {
  Element.prototype.animate = function () {
    return {
      play() {},
      pause() {},
      cancel() {},
      finish() {},
      playState: "running",
      onfinish: null,
      addEventListener() {},
      removeEventListener() {},
    } as any;
  };
}

/**
 * jsdom does not implement `matchMedia` and `ResizeObserver`. The theme
 * provider (next-themes) and the charts (recharts) need them, so the two
 * APIs are stubbed here.
 */
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }

  if (!window.ResizeObserver) {
    window.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof window.ResizeObserver;
  }

  if (!window.IntersectionObserver) {
    window.IntersectionObserver = class IntersectionObserver {
      readonly root: Element | Document | null = null;
      readonly rootMargin: string = "";
      readonly thresholds: ReadonlyArray<number> = [];
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    } as unknown as typeof window.IntersectionObserver;
    globalThis.IntersectionObserver = window.IntersectionObserver;
  }

  if (typeof SVGGeometryElement === "undefined") {
    class MockSVGGeometryElement extends (window.SVGElement || Object) {}
    (window as any).SVGGeometryElement = MockSVGGeometryElement;
    (globalThis as any).SVGGeometryElement = MockSVGGeometryElement;
  }

  if (!Element.prototype.animate) {
    Element.prototype.animate = function () {
      return {
        play() {},
        pause() {},
        cancel() {},
        finish() {},
        playState: "running",
        onfinish: null,
      } as any;
    };
  }
}
