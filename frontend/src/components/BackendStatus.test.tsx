import { screen } from "@testing-library/react";

import { jsonResponse, mockFetch, renderWithClient } from "../test/utils";
import { BackendStatus } from "./BackendStatus";

describe("BackendStatus", () => {
  it("shows ok when all dependencies are healthy", async () => {
    mockFetch(() => jsonResponse({ status: "ok", db: "ok", redis: "ok" }));

    renderWithClient(<BackendStatus />);

    expect(await screen.findByText("Backend: ok")).toHaveAttribute("data-state", "ok");
  });

  it("shows degraded when the backend returns a 503 health report", async () => {
    mockFetch(() => jsonResponse({ status: "degraded", db: "ok", redis: "error" }, 503));

    renderWithClient(<BackendStatus />);

    expect(await screen.findByText("Backend: degraded")).toHaveAttribute("data-state", "degraded");
  });

  it("shows unreachable when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    renderWithClient(<BackendStatus />);

    expect(await screen.findByText("Backend: unreachable")).toBeInTheDocument();
  });
});
