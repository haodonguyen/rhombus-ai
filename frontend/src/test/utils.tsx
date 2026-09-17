import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import type { StoredFile } from "../api/files";
import type { Job } from "../api/jobs";

export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stub global fetch. The handler receives the parsed request URL and init. */
export function mockFetch(handler: (url: URL, init?: RequestInit) => Response) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(new URL(String(input), "http://localhost"), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function makeFile(key: string, overrides: Partial<StoredFile> = {}): StoredFile {
  return {
    key,
    size: 2048,
    last_modified: "2026-01-01T00:00:00Z",
    file_type: key.endsWith(".xlsx") ? "xlsx" : "csv",
    ...overrides,
  };
}

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    status: "QUEUED",
    stage: "",
    progress: 0,
    source_bucket: "test-bucket",
    source_key: "samples/customers.csv",
    file_type: "csv",
    target_columns: ["Email"],
    transform_type: "regex_replace",
    transform_spec: null,
    nl_prompt: "",
    pattern: "@example\\.com",
    pattern_explanation: "",
    llm_cached: null,
    replacement_value: "REDACTED",
    row_count: null,
    matched_count: null,
    error: null,
    cancel_requested: false,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}
