import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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

  it("shows the description while the regex is being generated", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          status: "RUNNING",
          stage: "GENERATING_REGEX",
          progress: 5,
          nl_prompt: "email addresses",
          pattern: "",
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("Generating regex…")).toBeInTheDocument();
    expect(screen.getByText("email addresses")).toBeInTheDocument();
    expect(screen.getByText("Generating…")).toBeInTheDocument();
  });

  it("shows the generated pattern, its explanation and a cache hit", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          status: "SUCCESS",
          progress: 100,
          nl_prompt: "email addresses",
          pattern: "\\S+@\\S+",
          pattern_explanation: "Matches email addresses.",
          llm_cached: true,
          row_count: 3,
          matched_count: 3,
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("\\S+@\\S+")).toBeInTheDocument();
    expect(screen.getByText("Matches email addresses.")).toBeInTheDocument();
    expect(screen.getByText("cached")).toBeInTheDocument();
  });

  it("shows the error for failed jobs", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          status: "FAILED",
          error: { code: "PATTERN_NOT_EXPRESSIBLE", message: "Sentiment is not a pattern." },
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "PATTERN_NOT_EXPRESSIBLE Sentiment is not a pattern.",
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

  it("cancels a running job", async () => {
    const running = makeJob({ status: "RUNNING", stage: "TRANSFORMING", progress: 40 });
    const fetchMock = mockFetch((_url, init) =>
      init?.method === "POST"
        ? jsonResponse({ ...running, cancel_requested: true }, 202)
        : jsonResponse(running),
    );

    renderWithClient(<JobStatus jobId="job-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel job" }));

    expect(await screen.findByRole("button", { name: "Cancelling…" })).toBeDisabled();
    const cancelCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(cancelCall?.[0])).toContain("/api/jobs/job-1/cancel/");
  });

  it("shows a cancelled job as a notice rather than an error", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          status: "FAILED",
          error: { code: "CANCELLED", message: "The job was cancelled." },
          cancel_requested: true,
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("This job was cancelled.")).toBeInTheDocument();
    expect(screen.getByText("CANCELLED")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("offers no cancel button once the job has finished", async () => {
    mockFetch(() => jsonResponse(makeJob({ status: "SUCCESS", progress: 100 })));

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("SUCCESS")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel job" })).not.toBeInTheDocument();
  });
});
