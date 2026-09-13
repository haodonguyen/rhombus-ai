const API_BASE = "/api";

export type FieldErrors = Record<string, string[]>;

/** Error raised for non-2xx responses. Mirrors the backend `{"error": {code, message, details}}`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly body: unknown;

  constructor(status: number, code: string, message: string, details: unknown, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.body = body;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: unknown };
}

function toApiError(status: number, body: unknown): ApiError {
  const error = (body as ErrorBody | null)?.error;
  return new ApiError(
    status,
    error?.code ?? "HTTP_ERROR",
    error?.message ?? `Request failed with status ${status}`,
    error?.details,
    body,
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init.headers },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function withQuery(
  path: string,
  params: Record<string, string | number | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) {
    return "Could not reach the server. Check your connection and try again.";
  }
  return "Something went wrong. Please try again.";
}

/** Per-field messages from a VALIDATION_ERROR response, e.g. `{pattern: ["Invalid …"]}`. */
export function fieldErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiError) || typeof error.details !== "object" || !error.details) {
    return {};
  }
  const result: FieldErrors = {};
  for (const [field, messages] of Object.entries(error.details)) {
    if (Array.isArray(messages)) result[field] = messages.map(String);
  }
  return result;
}
