const API_BASE = "/api";

/** Error raised for non-2xx responses. Mirrors the backend `{"error": {code, message}}` shape. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly body: unknown;

  constructor(status: number, code: string, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string };
}

function toApiError(status: number, body: unknown): ApiError {
  const error = (body as ErrorBody | null)?.error;
  return new ApiError(
    status,
    error?.code ?? "HTTP_ERROR",
    error?.message ?? `Request failed with status ${status}`,
    body,
  );
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}
