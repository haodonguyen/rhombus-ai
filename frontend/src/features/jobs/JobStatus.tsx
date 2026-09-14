import { useMutation, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import {
  cancelJob,
  isNormalizationSpec,
  type Job,
  type PiiType,
  type TransformType,
} from "../../api/jobs";
import { formatNumber, formatStage } from "../../lib/format";
import { isTerminal } from "./polling";
import { jobQueryKey, useJob } from "./useJob";

const CANCELLED_CODE = "CANCELLED";

const TRANSFORM_LABELS: Record<TransformType, string> = {
  regex_replace: "Find & replace",
  normalize_format: "Normalize format",
  mask_pii: "Mask personal data",
};

const MATCHED_LABELS: Record<TransformType, string> = {
  regex_replace: "Rows matched",
  normalize_format: "Rows normalized",
  mask_pii: "Rows masked",
};

const UNCHANGED_NOTICES: Record<TransformType, string> = {
  regex_replace: "No values matched the pattern, so the data is unchanged.",
  normalize_format: "No values were in a recognised format, so the data is unchanged.",
  mask_pii: "No personal data was found in the selected columns, so the data is unchanged.",
};

export function JobStatus({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const { data: job, error, isPending } = useJob(jobId);
  const cancel = useMutation({
    mutationFn: () => cancelJob(jobId),
    onSuccess: (updated) => queryClient.setQueryData(jobQueryKey(jobId), updated),
  });

  if (isPending) return <p className="muted">Loading job…</p>;
  if (!job) {
    return (
      <div className="alert" role="alert">
        {describeError(error)}
      </div>
    );
  }

  const transform = job.transform_type;
  const finished = isTerminal(job.status);
  const cancelled = job.error?.code === CANCELLED_CODE;
  const cancelling = !finished && (job.cancel_requested || cancel.isPending);

  return (
    <div className="job-status">
      <div className="job-status-header" aria-live="polite">
        <span className="badge" data-status={job.status}>
          {cancelled ? "CANCELLED" : job.status}
        </span>
        {!finished && job.stage && <span className="muted">{formatStage(job.stage)}…</span>}
        {!finished && (
          <button
            type="button"
            className="secondary"
            onClick={() => cancel.mutate()}
            disabled={cancelling}
          >
            {cancelling ? "Cancelling…" : "Cancel job"}
          </button>
        )}
      </div>

      <div className="progress-row">
        <progress max={100} value={job.progress} aria-label="Job progress" />
        <span className="muted">{job.progress}%</span>
      </div>

      <dl className="job-meta">
        <dt>Transformation</dt>
        <dd>{TRANSFORM_LABELS[transform]}</dd>
        <dt>File</dt>
        <dd>{job.source_key}</dd>
        <dt>Columns</dt>
        <dd>{job.target_columns.join(", ")}</dd>
        {job.nl_prompt && (
          <>
            <dt>{transform === "normalize_format" ? "Target format" : "Description"}</dt>
            <dd>{job.nl_prompt}</dd>
          </>
        )}
        {transform === "regex_replace" ? (
          <>
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
          </>
        ) : (
          <>
            <dt>{transform === "mask_pii" ? "Detected" : "Specification"}</dt>
            <dd>
              <SpecSummary job={job} finished={finished} />
              {job.llm_cached && <span className="badge subtle">cached</span>}
            </dd>
          </>
        )}
        {job.pattern_explanation && (
          <>
            <dt>Explanation</dt>
            <dd>{job.pattern_explanation}</dd>
          </>
        )}
        {transform === "regex_replace" && (
          <>
            <dt>Replacement</dt>
            <dd>
              <code>{job.replacement_value || "(empty)"}</code>
            </dd>
          </>
        )}
        {job.status === "SUCCESS" && (
          <>
            <dt>Rows</dt>
            <dd>{formatNumber(job.row_count)}</dd>
            <dt>{MATCHED_LABELS[transform]}</dt>
            <dd>{formatNumber(job.matched_count)}</dd>
          </>
        )}
      </dl>

      {cancel.isError && (
        <div className="alert" role="alert">
          {describeError(cancel.error)}
        </div>
      )}
      {job.status === "SUCCESS" && job.matched_count === 0 && (
        <p className="notice">{UNCHANGED_NOTICES[transform]}</p>
      )}
      {job.error &&
        (cancelled ? (
          <p className="notice">This job was cancelled.</p>
        ) : (
          <div className="alert" role="alert">
            <strong>{job.error.code}</strong> {job.error.message}
          </div>
        ))}
      {error && !finished && (
        <p className="muted">Lost connection while refreshing status. Retrying…</p>
      )}
    </div>
  );
}

/** The LLM specification of a normalization or masking job, in readable form. */
function SpecSummary({ job, finished }: { job: Job; finished: boolean }) {
  const spec = job.transform_spec;
  if (spec === null) {
    return <span className="muted">{finished ? "—" : "Generating…"}</span>;
  }

  if (isNormalizationSpec(spec)) {
    if (spec.kind === "date") {
      return (
        <span>
          Reads <code>{spec.input_formats.join(", ")}</code>, writes{" "}
          <code>{spec.output_format}</code>
        </span>
      );
    }
    return (
      <ul className="spec-list">
        {spec.rules.map((rule, index) => (
          <li key={index}>
            <code>{rule.pattern}</code> → <code>{rule.replacement}</code>
          </li>
        ))}
      </ul>
    );
  }

  const detected = spec.columns
    .map(({ column, pii_types }) => ({ column, types: pii_types.filter((t) => t !== "none") }))
    .filter(({ types }) => types.length > 0);
  if (detected.length === 0) return <span>No personal data detected</span>;
  return (
    <ul className="spec-list">
      {detected.map(({ column, types }) => (
        <li key={column}>
          <strong>{column}</strong>: {types.map(formatPiiType).join(", ")}
        </li>
      ))}
    </ul>
  );
}

function formatPiiType(type: PiiType): string {
  return type.replaceAll("_", " ");
}
