import { screen } from "@testing-library/react";

import { jsonResponse, makeJob, mockFetch, renderWithClient } from "../../test/utils";
import { JobStatus } from "./JobStatus";

describe("JobStatus", () => {
  it("shows stage and progress while running", async () => {
    mockFetch(() =>
      jsonResponse(makeJob({ status: "RUNNING", stage: "TRANSFORMING", progress: 30 })),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("RUNNING")).toBeInTheDocument();
    expect(screen.getByText("Transforming…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Job progress" })).toHaveAttribute(
      "value",
      "30",
    );
  });

  it("shows the error for failed jobs", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          status: "FAILED",
          error: { code: "COLUMN_NOT_FOUND", message: "Column(s) not found: Phone" },
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "COLUMN_NOT_FOUND Column(s) not found: Phone",
    );
  });

  it("reports counts and explains when nothing matched", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({ status: "SUCCESS", progress: 100, row_count: 1200, matched_count: 0 }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("1,200")).toBeInTheDocument();
    expect(screen.getByText(/No values matched the pattern/)).toBeInTheDocument();
  });
});
