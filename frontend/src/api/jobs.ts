import { apiGet, apiPost, withQuery } from "./client";
import type { FileType } from "./files";

export type JobStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED";

export type TransformType = "regex_replace" | "normalize_format" | "mask_pii";

export type PiiType =
  "none" | "email" | "phone" | "person_name" | "credit_card" | "identifier" | "address" | "other";

/** LLM specification saved on a normalize_format job. */
export interface NormalizationSpec {
  feasible: boolean;
  kind: "date" | "rules";
  input_formats: string[];
  output_format: string;
  rules: { pattern: string; replacement: string }[];
  explanation: string;
}

/** LLM specification saved on a mask_pii job. */
export interface PiiClassification {
  columns: { column: string; pii_types: PiiType[] }[];
  explanation: string;
}

export interface Job {
  id: string;
  status: JobStatus;
  stage: string;
  progress: number;
  source_key: string;
  file_type: FileType;
  target_columns: string[];
  transform_type: TransformType;
  /** Description of what to find, or of the target format; empty for other jobs. */
  nl_prompt: string;
  /** Applied regex. Empty until generated when the job was submitted with a description. */
  pattern: string;
  /** The LLM's explanation of the generated pattern or specification. */
  pattern_explanation: string;
  /** Saved LLM specification for normalize_format and mask_pii jobs; null until generated. */
  transform_spec: NormalizationSpec | PiiClassification | null;
  /** Whether the LLM answer came from the cache; null when no LLM was involved. */
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

export function isNormalizationSpec(spec: Job["transform_spec"]): spec is NormalizationSpec {
  return spec !== null && "kind" in spec;
}

interface JobTarget {
  source_key: string;
  target_columns: string[];
}

/** Find and replace takes exactly one of `nl_prompt` or `pattern`. */
export type CreateJob =
  | (JobTarget & { transform_type: "regex_replace"; replacement_value: string } & (
        { nl_prompt: string; pattern?: never } | { pattern: string; nl_prompt?: never }
      ))
  | (JobTarget & { transform_type: "normalize_format"; nl_prompt: string })
  | (JobTarget & { transform_type: "mask_pii" });

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

export function createJob(payload: CreateJob): Promise<Job> {
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
