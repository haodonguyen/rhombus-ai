import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { NormalizationSpec, PiiClassification } from "../../api/jobs";
import { jsonResponse, makeJob, mockFetch, renderWithClient } from "../../test/utils";
import { JobStatus } from "./JobStatus";

const DATE_SPEC: NormalizationSpec = {
  feasible: true,
  kind: "date",
  input_formats: ["yyyy-MM-dd", "dd/MM/yyyy"],
  output_format: "yyyy-MM-dd",
  rules: [],
  explanation: "Writes dates as YYYY-MM-DD.",
};

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

  it("shows a normalization job's target format, date spec and normalized rows", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          transform_type: "normalize_format",
          status: "SUCCESS",
          progress: 100,
          nl_prompt: "dates as YYYY-MM-DD",
          pattern: "",
          replacement_value: "",
          pattern_explanation: DATE_SPEC.explanation,
          transform_spec: DATE_SPEC,
          row_count: 3,
          matched_count: 2,
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("Normalize format")).toBeInTheDocument();
    expect(screen.getByText("Target format")).toBeInTheDocument();
    expect(screen.getByText("yyyy-MM-dd, dd/MM/yyyy")).toBeInTheDocument();
    expect(screen.getByText("Rows normalized")).toBeInTheDocument();
    expect(screen.queryByText("Pattern")).not.toBeInTheDocument();
    expect(screen.queryByText("Replacement")).not.toBeInTheDocument();
  });

  it("lists rewrite rules for non-date normalization", async () => {
    const spec: NormalizationSpec = {
      ...DATE_SPEC,
      kind: "rules",
      input_formats: [],
      output_format: "",
      rules: [{ pattern: "^(\\d{3})\\.(\\d{4})$", replacement: "$1-$2" }],
    };
    mockFetch(() =>
      jsonResponse(makeJob({ transform_type: "normalize_format", transform_spec: spec })),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("^(\\d{3})\\.(\\d{4})$")).toBeInTheDocument();
    expect(screen.getByText("$1-$2")).toBeInTheDocument();
  });

  it("shows the spec as generating while a spec job samples the data", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          transform_type: "normalize_format",
          status: "RUNNING",
          stage: "GENERATING_SPEC",
          progress: 8,
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("Generating spec…")).toBeInTheDocument();
    expect(screen.getByText("Generating…")).toBeInTheDocument();
  });

  it("lists the columns detected as personal data", async () => {
    const spec: PiiClassification = {
      columns: [
        { column: "ID", pii_types: ["none"] },
        { column: "Email", pii_types: ["email"] },
        { column: "Notes", pii_types: ["phone", "credit_card"] },
      ],
      explanation: "Email and Notes contain personal data.",
    };
    mockFetch(() =>
      jsonResponse(
        makeJob({
          transform_type: "mask_pii",
          status: "SUCCESS",
          progress: 100,
          transform_spec: spec,
          row_count: 5,
          matched_count: 4,
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("Mask personal data")).toBeInTheDocument();
    const detected = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(detected).toEqual(["Email: email", "Notes: phone, credit card"]);
    expect(screen.getByText("Rows masked")).toBeInTheDocument();
  });

  it("explains when no personal data was found", async () => {
    mockFetch(() =>
      jsonResponse(
        makeJob({
          transform_type: "mask_pii",
          status: "SUCCESS",
          progress: 100,
          transform_spec: { columns: [{ column: "ID", pii_types: ["none"] }], explanation: "" },
          row_count: 5,
          matched_count: 0,
        }),
      ),
    );

    renderWithClient(<JobStatus jobId="job-1" />);

    expect(await screen.findByText("No personal data detected")).toBeInTheDocument();
    expect(screen.getByText(/No personal data was found/)).toBeInTheDocument();
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
