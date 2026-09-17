import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, mockFetch, renderWithClient } from "../../test/utils";
import { ColumnPicker } from "./ColumnPicker";

const preview = {
  key: "a.csv",
  file_type: "csv",
  columns: ["ID", "Name", "Email"],
  sample_rows: [["1", "John Doe", "john@example.com"]],
};

describe("ColumnPicker", () => {
  it("shows columns with sample rows and keeps selections in file order", async () => {
    mockFetch(() => jsonResponse(preview));
    const onChange = vi.fn();

    renderWithClient(
      <ColumnPicker
        connectionId="conn-1"
        fileKey="a.csv"
        selected={["Email"]}
        onChange={onChange}
      />,
    );
    await userEvent.click(await screen.findByRole("checkbox", { name: "ID" }));

    expect(onChange).toHaveBeenCalledWith(["ID", "Email"]);
    expect(screen.getByRole("checkbox", { name: "Email" })).toBeChecked();
    expect(screen.getByText("john@example.com")).toBeInTheDocument();
  });

  it("unchecking removes the column", async () => {
    mockFetch(() => jsonResponse(preview));
    const onChange = vi.fn();

    renderWithClient(
      <ColumnPicker
        connectionId="conn-1"
        fileKey="a.csv"
        selected={["Name", "Email"]}
        onChange={onChange}
      />,
    );
    await userEvent.click(await screen.findByRole("checkbox", { name: "Name" }));

    expect(onChange).toHaveBeenCalledWith(["Email"]);
  });

  it("explains when the file has no columns", async () => {
    mockFetch(() => jsonResponse({ ...preview, columns: [], sample_rows: [] }));

    renderWithClient(
      <ColumnPicker connectionId="conn-1" fileKey="a.csv" selected={[]} onChange={vi.fn()} />,
    );

    expect(await screen.findByText(/no header row/)).toBeInTheDocument();
  });
});
