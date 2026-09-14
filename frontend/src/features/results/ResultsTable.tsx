import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { describeError } from "../../api/client";
import { fetchJobResults } from "../../api/jobs";
import { formatNumber } from "../../lib/format";

const PAGE_SIZES = [25, 50, 100];

export function ResultsTable({ jobId }: { jobId: string }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const query = useQuery({
    queryKey: ["job-results", jobId, page, pageSize],
    queryFn: () => fetchJobResults(jobId, page, pageSize),
    // Keep the current page on screen while the next one loads.
    placeholderData: keepPreviousData,
  });

  if (query.isPending) return <p className="muted">Loading results…</p>;
  if (!query.data) {
    return (
      <div className="alert" role="alert">
        {describeError(query.error)}
      </div>
    );
  }

  const results = query.data;
  if (results.total_rows === 0) {
    return <p className="muted">The file has no data rows.</p>;
  }

  return (
    <div className="results">
      {query.isError && (
        <div className="alert" role="alert">
          {describeError(query.error)}
        </div>
      )}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              {results.columns.map((column, index) => (
                <th key={`${index}-${column}`} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.rows.map((row) => (
              <tr key={row.row_number} className={row.matched ? "matched" : undefined}>
                <td className="muted">{row.row_number}</td>
                {row.values.map((value, index) => (
                  <td key={index}>{value ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <nav className="pagination" aria-label="Results pages">
        <button
          type="button"
          className="secondary"
          onClick={() => setPage((current) => current - 1)}
          disabled={page <= 1 || query.isFetching}
        >
          Previous
        </button>
        <span>
          Page {results.page} of {formatNumber(results.total_pages)} ·{" "}
          {formatNumber(results.total_rows)} rows
        </span>
        <button
          type="button"
          className="secondary"
          onClick={() => setPage((current) => current + 1)}
          disabled={page >= results.total_pages || query.isFetching}
        >
          Next
        </button>
        <label>
          Rows per page{" "}
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </nav>
    </div>
  );
}
