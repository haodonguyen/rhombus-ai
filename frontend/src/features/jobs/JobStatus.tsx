import { describeError } from "../../api/client";
import { formatNumber, formatStage } from "../../lib/format";
import { isTerminal } from "./polling";
import { useJob } from "./useJob";

export function JobStatus({ jobId }: { jobId: string }) {
  const { data: job, error, isPending } = useJob(jobId);

  if (isPending) return <p className="muted">Loading job…</p>;
  if (!job) {
    return (
      <div className="alert" role="alert">
        {describeError(error)}
      </div>
    );
  }

  const finished = isTerminal(job.status);

  return (
    <div className="job-status">
      <div className="job-status-header" aria-live="polite">
        <span className="badge" data-status={job.status}>
          {job.status}
        </span>
        {!finished && job.stage && <span className="muted">{formatStage(job.stage)}…</span>}
      </div>

      <div className="progress-row">
        <progress max={100} value={job.progress} aria-label="Job progress" />
        <span className="muted">{job.progress}%</span>
      </div>

      <dl className="job-meta">
        <dt>File</dt>
        <dd>{job.source_key}</dd>
        <dt>Columns</dt>
        <dd>{job.target_columns.join(", ")}</dd>
        {job.nl_prompt && (
          <>
            <dt>Description</dt>
            <dd>{job.nl_prompt}</dd>
          </>
        )}
        <dt>Pattern</dt>
        <dd>
          {job.pattern ? (
            <>
              <code>{job.pattern}</code>
              {job.llm_cached && <span className="badge subtle">cached</span>}
            </>
          ) : (
            <span className="muted">{finished ? "—" : "Generating…"}</span>
          )}
        </dd>
        {job.pattern_explanation && (
          <>
            <dt>Explanation</dt>
            <dd>{job.pattern_explanation}</dd>
          </>
        )}
        <dt>Replacement</dt>
        <dd>
          <code>{job.replacement_value || "(empty)"}</code>
        </dd>
        {job.status === "SUCCESS" && (
          <>
            <dt>Rows</dt>
            <dd>{formatNumber(job.row_count)}</dd>
            <dt>Rows matched</dt>
            <dd>{formatNumber(job.matched_count)}</dd>
          </>
        )}
      </dl>

      {job.status === "SUCCESS" && job.matched_count === 0 && (
        <p className="notice">No values matched the pattern, so the data is unchanged.</p>
      )}
      {job.error && (
        <div className="alert" role="alert">
          <strong>{job.error.code}</strong> {job.error.message}
        </div>
      )}
      {error && !finished && (
        <p className="muted">Lost connection while refreshing status. Retrying…</p>
      )}
    </div>
  );
}
