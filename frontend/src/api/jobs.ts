import { apiGet, apiPost, withQuery } from "./client";
import type { FileType } from "./files";

export type JobStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED";

export interface Job {
  id: string;
  status: JobStatus;
  stage: string;
  progress: number;
  source_key: string;
  file_type: FileType;
  target_columns: string[];
  transform_type: string;
  /** Plain-English description; empty when the user entered a regex directly. */
  nl_prompt: string;
  /** Applied regex. Empty until generated when the job was submitted with a description. */
  pattern: string;
  pattern_explanation: string;
  /** Whether the generated pattern came from the cache; null when no LLM was involved. */
  llm_cached: boolean | null;
  replacement_value: string;
  row_count: number | null;
  matched_count: number | null;
  /** A cancelled job is FAILED with error code CANCELLED. */
  error: { code: string; message: string } | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/** Provide exactly one of `nl_prompt` or `pattern`. */
export type CreateRegexReplaceJob = {
  source_key: string;
  target_columns: string[];
  replacement_value: string;
} & ({ nl_prompt: string; pattern?: never } | { pattern: string; nl_prompt?: never });

export interface ResultRow {
  row_number: number;
  matched: boolean;
  values: (string | null)[];
}

export interface ResultsPage {
  columns: string[];
  rows: ResultRow[];
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
}

export function createJob(payload: CreateRegexReplaceJob): Promise<Job> {
  return apiPost("/jobs/", payload);
}

export function fetchJob(jobId: string): Promise<Job> {
  return apiGet(`/jobs/${encodeURIComponent(jobId)}/`);
}

export function cancelJob(jobId: string): Promise<Job> {
  return apiPost(`/jobs/${encodeURIComponent(jobId)}/cancel/`, {});
}

export function fetchJobResults(
  jobId: string,
  page: number,
  pageSize: number,
): Promise<ResultsPage> {
  return apiGet(
    withQuery(`/jobs/${encodeURIComponent(jobId)}/results/`, { page, page_size: pageSize }),
  );
}
