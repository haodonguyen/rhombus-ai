import type { JobStatus } from "../../api/jobs";

const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>(["SUCCESS", "FAILED"]);

export const MIN_POLL_MS = 1000;
export const MAX_POLL_MS = 5000;

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

/** Poll quickly while a job starts, then back off: 1s, 1.5s, 2.25s … capped at 5s. */
export function pollInterval(attempt: number): number {
  return Math.min(MIN_POLL_MS * 1.5 ** attempt, MAX_POLL_MS);
}
