/**
 * Typed fetch wrapper for the PartPilot backend.
 *
 * NFR-07: the frontend NEVER calls a distributor API or an LLM directly.
 * Every request goes to the PartPilot backend under `/api/...` (or to the MSW
 * mock which serves the very same paths in development).
 *
 * No API key, token or secret ever lives in this file or anywhere else in
 * the frontend (rule 3).
 */

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly code?: string;

  constructor(status: number, detail: string, code?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
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
  return new ApiError(response.status, detail, code);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "The PartPilot backend is unreachable.");
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
export function apiGet<T>(path: string, params?: Record<string, QueryValue>): Promise<T> {
  return request<T>(`${path}${buildQuery(params)}`);
}

/** `POST` a JSON body. */
export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/**
 * `POST` a multipart upload (the BOM CSV).
 *
 * The multipart body is assembled by hand instead of with `FormData`. In the
 * jsdom test environment `FormData` and the fetch implementation of Node do
 * not agree on the body, and the request never reaches the server. The body
 * that is built here is a standard `multipart/form-data` body and is accepted
 * by the backend as well as by the mock.
 */
export async function apiUpload<T>(path: string, file: File, fieldName = "file"): Promise<T> {
  const boundary = `----partpilot${Math.random().toString(36).slice(2)}`;
  const header = [
    `--${boundary}`,
    `Content-Disposition: form-data; name="${fieldName}"; filename="${file.name.replace(/"/g, "")}"`,
    `Content-Type: ${file.type || "application/octet-stream"}`,
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
  });
}

/** Human readable message for any error that can reach the UI. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
