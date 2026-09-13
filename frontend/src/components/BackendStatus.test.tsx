import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { BackendStatus } from "./BackendStatus";

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackendStatus />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BackendStatus", () => {
  it("shows ok when all dependencies are healthy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ status: "ok", db: "ok", redis: "ok" }, 200)),
    );

    renderWithClient();

    expect(await screen.findByText("Backend: ok")).toHaveAttribute("data-state", "ok");
  });

  it("shows degraded when the backend returns a 503 health report", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(jsonResponse({ status: "degraded", db: "ok", redis: "error" }, 503)),
    );

    renderWithClient();

    expect(await screen.findByText("Backend: degraded")).toHaveAttribute("data-state", "degraded");
  });

  it("shows unreachable when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    renderWithClient();

    expect(await screen.findByText("Backend: unreachable")).toBeInTheDocument();
  });
});
