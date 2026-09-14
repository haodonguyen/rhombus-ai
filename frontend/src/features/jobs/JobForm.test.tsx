import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, makeJob, mockFetch, renderWithClient } from "../../test/utils";
import { JobForm } from "./JobForm";

function requestBody(fetchMock: ReturnType<typeof mockFetch>): unknown {
  return JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
}

const TARGET = { source_key: "a.csv", target_columns: ["Email"] };

describe("JobForm", () => {
  it("is disabled until a column and a description are provided", async () => {
    mockFetch(() => jsonResponse(makeJob(), 202));

    renderWithClient(<JobForm sourceKey="a.csv" targetColumns={[]} onSubmitted={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Describe what to find"), "email addresses");

    expect(screen.getByRole("button", { name: "Run job" })).toBeDisabled();
    expect(screen.getByText(/Select at least one target column/)).toBeInTheDocument();
  });

  it("submits a plain-English description for find and replace", async () => {
    const job = makeJob({ nl_prompt: "email addresses", pattern: "" });
    const fetchMock = mockFetch(() => jsonResponse(job, 202));
    const onSubmitted = vi.fn();

    renderWithClient(
      <JobForm sourceKey="a.csv" targetColumns={["Email"]} onSubmitted={onSubmitted} />,
    );
    await userEvent.type(screen.getByLabelText("Describe what to find"), "  email addresses ");
    await userEvent.type(screen.getByLabelText("Replacement value"), "REDACTED");
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(job));
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(requestBody(fetchMock)).toEqual({
      ...TARGET,
      transform_type: "regex_replace",
      replacement_value: "REDACTED",
      nl_prompt: "email addresses",
    });
  });

  it("can submit a raw regex instead", async () => {
    const fetchMock = mockFetch(() => jsonResponse(makeJob(), 202));

    renderWithClient(<JobForm sourceKey="a.csv" targetColumns={["Email"]} onSubmitted={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Enter a regex instead" }));
    await userEvent.type(screen.getByLabelText("Regex pattern"), "@example");
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(requestBody(fetchMock)).toEqual({
      ...TARGET,
      transform_type: "regex_replace",
      replacement_value: "",
      pattern: "@example",
    });
  });

  it("submits a target format for normalization", async () => {
    const fetchMock = mockFetch(() =>
      jsonResponse(makeJob({ transform_type: "normalize_format" }), 202),
    );

    renderWithClient(<JobForm sourceKey="a.csv" targetColumns={["Email"]} onSubmitted={vi.fn()} />);
    await userEvent.click(screen.getByRole("radio", { name: /Normalize format/ }));

    expect(screen.queryByLabelText("Replacement value")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run job" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Target format"), "dates as YYYY-MM-DD");
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(requestBody(fetchMock)).toEqual({
      ...TARGET,
      transform_type: "normalize_format",
      nl_prompt: "dates as YYYY-MM-DD",
    });
  });

  it("submits a masking job without any description", async () => {
    const fetchMock = mockFetch(() => jsonResponse(makeJob({ transform_type: "mask_pii" }), 202));

    renderWithClient(<JobForm sourceKey="a.csv" targetColumns={["Email"]} onSubmitted={vi.fn()} />);
    await userEvent.click(screen.getByRole("radio", { name: /Mask personal data/ }));

    expect(screen.queryByLabelText("Describe what to find")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(requestBody(fetchMock)).toEqual({ ...TARGET, transform_type: "mask_pii" });
  });

  it("shows field errors returned by the API", async () => {
    mockFetch(() =>
      jsonResponse(
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "The request contains invalid fields.",
            details: { pattern: ["Invalid regular expression: missing )"] },
          },
        },
        400,
      ),
    );

    renderWithClient(<JobForm sourceKey="a.csv" targetColumns={["Email"]} onSubmitted={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Enter a regex instead" }));
    await userEvent.type(screen.getByLabelText("Regex pattern"), "(oops");
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    expect(await screen.findByText(/Invalid regular expression/)).toBeInTheDocument();
    expect(screen.getByLabelText("Regex pattern")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("The request contains invalid fields.");
  });
});
