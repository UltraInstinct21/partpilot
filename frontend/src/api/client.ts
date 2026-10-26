/**
 * Typed fetch wrapper for the PartPilot backend.
 *
 * NFR-07: the frontend NEVER calls a distributor API or an LLM directly.
 * Every request goes to the PartPilot backend under `/api/...` (or to the MSW
 * mock which serves the very same paths in development).
 *
 * No API key, token or secret ever lives in this file or anywhere else in
 * the frontend.
 */

export interface NormalizedError {
  status: number;
  code?: string;
  message: string;
  retryAfter?: number;
}

export class ApiError extends Error implements NormalizedError {
  readonly status: number;
  readonly detail: string;
  readonly code?: string;
  readonly retryAfter?: number;

  constructor(status: number, detail: string, code?: string, retryAfter?: number) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

/** Optional prefix, e.g. `http://127.0.0.1:8000`. Empty means "same origin". */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export type QueryValue = string | number | boolean | undefined | null;

export function buildQuery(params?: Record<string, QueryValue>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = `Request failed (HTTP ${response.status}).`;
  let code: string | undefined;

  const retryAfterHeader = response.headers?.get("Retry-After");
  const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined;

  try {
    const body = (await response.json()) as { detail?: unknown; error?: unknown; code?: unknown };
    if (typeof body?.detail === "string" && body.detail.length > 0) {
      detail = body.detail;
    } else if (typeof body?.error === "string" && body.error.length > 0) {
      detail = body.error;
    }
    if (typeof body?.code === "string") code = body.code;
  } catch {
    // The body was not JSON. The generic message above is used.
  }

  if (response.status === 429 && retryAfter) {
    detail = `Search rate limit reached. Please wait ${retryAfter} seconds before trying again.`;
  }

  return new ApiError(response.status, detail, code, retryAfter);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "The PartPilot backend is unreachable. Check that the API is running.");
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

/** `GET` a JSON resource. */
export function apiGet<T>(path: string, params?: Record<string, QueryValue>, signal?: AbortSignal): Promise<T> {
  return request<T>(`${path}${buildQuery(params)}`, { signal });
}

/** `POST` a JSON body. */
export function apiPost<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
}

/** Download a same-origin file while reporting byte progress to the UI. */
export async function downloadFileWithProgress(
  path: string,
  filename: string,
  onProgress?: (percent: number | null) => void,
): Promise<void> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) throw await parseError(response);

  const total = Number(response.headers.get("Content-Length")) || 0;
  if (!response.body) {
    saveBlob(await response.blob(), filename);
    onProgress?.(100);
    return;
  }

  const reader = response.body.getReader();
  const chunks: ArrayBuffer[] = [];
  let loaded = 0;
  onProgress?.(total > 0 ? 0 : null);
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer);
      loaded += value.byteLength;
      onProgress?.(total > 0 ? Math.min(99, Math.round((loaded / total) * 100)) : null);
    }
  }
  saveBlob(
    new Blob(chunks, { type: response.headers.get("Content-Type") || "application/pdf" }),
    filename,
  );
  onProgress?.(100);
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * `POST` a multipart upload (the BOM CSV).
 */
export async function apiUpload<T>(path: string, file: File, fieldName = "file", signal?: AbortSignal): Promise<T> {
  const boundary = `----partpilot${Math.random().toString(36).slice(2)}`;
  const header = [
    `--${boundary}`,
    `Content-Disposition: form-data; name="${fieldName}"; filename="${file.name.replace(/"/g, "")}"`,
    `Content-Type: ${file.type || "text/csv"}`,
    "",
    "",
  ].join("\r\n");
  const footer = `\r\n--${boundary}--\r\n`;

  const prefix = new TextEncoder().encode(header);
  const content = new Uint8Array(await file.arrayBuffer());
  const suffix = new TextEncoder().encode(footer);
  const body = new Uint8Array(prefix.length + content.length + suffix.length);
  body.set(prefix, 0);
  body.set(content, prefix.length);
  body.set(suffix, prefix.length + content.length);

  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` },
    body,
    signal,
  });
}

/** Human readable message for any error that can reach the UI. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}
