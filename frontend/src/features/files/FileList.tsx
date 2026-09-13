import { useInfiniteQuery } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import { fetchFiles } from "../../api/files";
import { formatBytes } from "../../lib/format";

interface FileListProps {
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export function FileList({ selectedKey, onSelect }: FileListProps) {
  const query = useInfiniteQuery({
    queryKey: ["files"],
    queryFn: ({ pageParam }) => fetchFiles(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });

  if (query.isPending) return <p className="muted">Loading files…</p>;

  if (query.isError) {
    return (
      <div className="alert" role="alert">
        <span>{describeError(query.error)}</span>
        <button type="button" className="secondary" onClick={() => void query.refetch()}>
          Retry
        </button>
      </div>
    );
  }

  const files = query.data.pages.flatMap((page) => page.files);
  if (files.length === 0) {
    return <p className="muted">No CSV or Excel files were found in the bucket.</p>;
  }

  return (
    <div>
      <ul className="file-list">
        {files.map((file) => (
          <li key={file.key}>
            <label className="file-option" data-selected={file.key === selectedKey}>
              <input
                type="radio"
                name="source-file"
                value={file.key}
                checked={file.key === selectedKey}
                onChange={() => onSelect(file.key)}
              />
              <span className="file-name">{file.key}</span>
              <span className="muted">
                {file.file_type.toUpperCase()} · {formatBytes(file.size)}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {query.hasNextPage && (
        <button
          type="button"
          className="secondary"
          onClick={() => void query.fetchNextPage()}
          disabled={query.isFetchingNextPage}
        >
          {query.isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
