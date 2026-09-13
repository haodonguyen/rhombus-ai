import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, makeFile, mockFetch, renderWithClient } from "../../test/utils";
import { FileList } from "./FileList";

describe("FileList", () => {
  it("lists files and reports the selected key", async () => {
    mockFetch(() =>
      jsonResponse({
        files: [makeFile("samples/a.csv"), makeFile("samples/b.xlsx")],
        next_cursor: null,
      }),
    );
    const onSelect = vi.fn();

    renderWithClient(<FileList selectedKey={null} onSelect={onSelect} />);
    await userEvent.click(await screen.findByLabelText(/samples\/b\.xlsx/));

    expect(onSelect).toHaveBeenCalledWith("samples/b.xlsx");
    expect(screen.getByText("XLSX · 2.0 KB")).toBeInTheDocument();
  });

  it("loads the next page with the cursor", async () => {
    const fetchMock = mockFetch((url) =>
      url.searchParams.get("cursor") === "b.csv"
        ? jsonResponse({ files: [makeFile("c.xlsx")], next_cursor: null })
        : jsonResponse({ files: [makeFile("a.csv"), makeFile("b.csv")], next_cursor: "b.csv" }),
    );

    renderWithClient(<FileList selectedKey={null} onSelect={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));

    expect(await screen.findByText("c.xlsx")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows an empty state", async () => {
    mockFetch(() => jsonResponse({ files: [], next_cursor: null }));

    renderWithClient(<FileList selectedKey={null} onSelect={vi.fn()} />);

    expect(await screen.findByText(/No CSV or Excel files/)).toBeInTheDocument();
  });

  it("shows the API error message and can retry", async () => {
    let calls = 0;
    mockFetch(() => {
      calls += 1;
      return calls === 1
        ? jsonResponse(
            { error: { code: "STORAGE_UNAVAILABLE", message: "File storage is unavailable." } },
            503,
          )
        : jsonResponse({ files: [makeFile("a.csv")], next_cursor: null });
    });

    renderWithClient(<FileList selectedKey={null} onSelect={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("File storage is unavailable.");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("a.csv")).toBeInTheDocument();
  });
});
