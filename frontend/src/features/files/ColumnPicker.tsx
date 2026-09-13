import { useQuery } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import { fetchFilePreview } from "../../api/files";

interface ColumnPickerProps {
  fileKey: string;
  selected: string[];
  onChange: (columns: string[]) => void;
}

export function ColumnPicker({ fileKey, selected, onChange }: ColumnPickerProps) {
  const query = useQuery({
    queryKey: ["file-preview", fileKey],
    queryFn: () => fetchFilePreview(fileKey),
  });

  if (query.isPending) return <p className="muted">Reading columns…</p>;
  if (query.isError) {
    return (
      <div className="alert" role="alert">
        {describeError(query.error)}
      </div>
    );
  }

  const { columns, sample_rows: sampleRows } = query.data;
  if (columns.length === 0) {
    return <p className="muted">This file has no header row, so there are no columns to pick.</p>;
  }

  function toggle(column: string) {
    const next = new Set(selected);
    if (next.has(column)) next.delete(column);
    else next.add(column);
    // Keep the file's column order regardless of click order.
    onChange(columns.filter((name) => next.has(name)));
  }

  return (
    <div className="column-picker">
      <fieldset>
        <legend>Target columns</legend>
        <div className="chips">
          {columns.map((column, index) => (
            <label key={`${index}-${column}`} className="chip">
              <input
                type="checkbox"
                checked={selected.includes(column)}
                onChange={() => toggle(column)}
              />
              {column}
            </label>
          ))}
        </div>
      </fieldset>

      {sampleRows.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <caption>Sample rows</caption>
            <thead>
              <tr>
                {columns.map((column, index) => (
                  <th key={`${index}-${column}`} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sampleRows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column, index) => (
                    <td key={`${index}-${column}`}>{row[index] ?? ""}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
