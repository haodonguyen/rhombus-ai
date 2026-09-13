import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, makeJob, mockFetch, renderWithClient } from "../../test/utils";
import { JobForm } from "./JobForm";

describe("JobForm", () => {
  it("is disabled until a column and pattern are provided", async () => {
    mockFetch(() => jsonResponse(makeJob(), 202));

    renderWithClient(<JobForm sourceKey="a.csv" targetColumns={[]} onSubmitted={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Regex pattern"), "@example");

    expect(screen.getByRole("button", { name: "Run job" })).toBeDisabled();
    expect(screen.getByText(/Select at least one target column/)).toBeInTheDocument();
  });

  it("submits the job and reports it", async () => {
    const job = makeJob();
    const fetchMock = mockFetch(() => jsonResponse(job, 202));
    const onSubmitted = vi.fn();

    renderWithClient(
      <JobForm sourceKey="a.csv" targetColumns={["Email"]} onSubmitted={onSubmitted} />,
    );
    await userEvent.type(screen.getByLabelText("Regex pattern"), "@example");
    await userEvent.type(screen.getByLabelText("Replacement value"), "REDACTED");
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(job));
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      source_key: "a.csv",
      target_columns: ["Email"],
      pattern: "@example",
      replacement_value: "REDACTED",
    });
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
    await userEvent.type(screen.getByLabelText("Regex pattern"), "(oops");
    await userEvent.click(screen.getByRole("button", { name: "Run job" }));

    expect(await screen.findByText(/Invalid regular expression/)).toBeInTheDocument();
    expect(screen.getByLabelText("Regex pattern")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("The request contains invalid fields.");
  });
});
