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

export function fetchFiles(cursor: string | null): Promise<FilePage> {
  return apiGet(withQuery("/files/", { cursor, page_size: FILE_PAGE_SIZE }));
}

export function fetchFilePreview(key: string): Promise<FilePreview> {
  return apiGet(withQuery("/files/columns/", { key }));
}
