import { apiGet, withQuery } from "./client";

export type FileType = "csv" | "xlsx";

export interface StoredFile {
  key: string;
  size: number;
  last_modified: string;
  file_type: FileType;
}

export interface FilePage {
  files: StoredFile[];
  next_cursor: string | null;
}

export interface FilePreview {
  key: string;
  file_type: FileType;
  columns: string[];
  sample_rows: (string | null)[][];
}

export const FILE_PAGE_SIZE = 50;

export function fetchFiles(connectionId: string, cursor: string | null): Promise<FilePage> {
  return apiGet(
    withQuery("/files/", { connection_id: connectionId, cursor, page_size: FILE_PAGE_SIZE }),
  );
}

export function fetchFilePreview(connectionId: string, key: string): Promise<FilePreview> {
  return apiGet(withQuery("/files/columns/", { connection_id: connectionId, key }));
}
