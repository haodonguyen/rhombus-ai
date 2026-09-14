import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ResultsPage } from "../../api/jobs";
import { jsonResponse, mockFetch, renderWithClient } from "../../test/utils";
import { ResultsTable } from "./ResultsTable";

function resultsPage(overrides: Partial<ResultsPage>): ResultsPage {
  return {
    columns: ["ID", "Name", "Email"],
    rows: [],
    page: 1,
    page_size: 2,
    total_rows: 3,
    total_pages: 2,
    ...overrides,
  };
}

const firstPage = resultsPage({
  rows: [
    { row_number: 1, matched: true, values: ["1", "John Doe", "REDACTED"] },
    { row_number: 2, matched: false, values: ["2", "Jane Smith", null] },
  ],
});

const secondPage = resultsPage({
  page: 2,
  rows: [{ row_number: 3, matched: true, values: ["3", "Alice Brown", "REDACTED"] }],
});

describe("ResultsTable", () => {
  it("renders rows, highlights matches and pages forward", async () => {
    const fetchMock = mockFetch((url) =>
      jsonResponse(url.searchParams.get("page") === "2" ? secondPage : firstPage),
    );

    renderWithClient(<ResultsTable jobId="job-1" />);

    expect((await screen.findByText("John Doe")).closest("tr")).toHaveClass("matched");
    expect(screen.getByText("Jane Smith").closest("tr")).not.toHaveClass("matched");
    // Spark reads empty CSV cells as null; show them as empty, like the source file.
    expect(screen.queryByText("null")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Alice Brown")).toBeInTheDocument();
    expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("page=2");
  });

  it("shows an empty state when the file has no rows", async () => {
    mockFetch(() => jsonResponse(resultsPage({ total_rows: 0, total_pages: 1 })));

    renderWithClient(<ResultsTable jobId="job-1" />);

    expect(await screen.findByText("The file has no data rows.")).toBeInTheDocument();
  });
});
