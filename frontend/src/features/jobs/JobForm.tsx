import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useId, useState } from "react";

import { describeError, fieldErrors } from "../../api/client";
import { createJob, type Job } from "../../api/jobs";
import { jobQueryKey } from "./useJob";

interface JobFormProps {
  sourceKey: string;
  targetColumns: string[];
  onSubmitted: (job: Job) => void;
}

export function JobForm({ sourceKey, targetColumns, onSubmitted }: JobFormProps) {
  const id = useId();
  const queryClient = useQueryClient();
  const [pattern, setPattern] = useState("");
  const [replacement, setReplacement] = useState("");

  const mutation = useMutation({
    mutationFn: createJob,
    onSuccess: (job) => {
      // Seed the cache so the status panel renders immediately, before the first poll.
      queryClient.setQueryData(jobQueryKey(job.id), job);
      onSubmitted(job);
    },
  });

  const errors = fieldErrors(mutation.error);
  const canSubmit = targetColumns.length > 0 && pattern.length > 0 && !mutation.isPending;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    mutation.mutate({
      source_key: sourceKey,
      target_columns: targetColumns,
      pattern,
      replacement_value: replacement,
    });
  }

  return (
    <form className="job-form" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor={`${id}-pattern`}>Regex pattern</label>
        <input
          id={`${id}-pattern`}
          className="mono"
          value={pattern}
          onChange={(event) => setPattern(event.target.value)}
          placeholder={String.raw`\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b`}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={errors.pattern ? true : undefined}
          aria-describedby={errors.pattern ? `${id}-pattern-error` : undefined}
        />
        <FieldError id={`${id}-pattern-error`} messages={errors.pattern} />
      </div>

      <div className="field">
        <label htmlFor={`${id}-replacement`}>Replacement value</label>
        <input
          id={`${id}-replacement`}
          value={replacement}
          onChange={(event) => setReplacement(event.target.value)}
          placeholder="REDACTED"
          autoComplete="off"
        />
        <FieldError messages={errors.replacement_value} />
      </div>

      <p className="muted">
        {targetColumns.length === 0
          ? "Select at least one target column above."
          : `Applies to: ${targetColumns.join(", ")}`}
      </p>
      <FieldError messages={errors.target_columns} />
      <FieldError messages={errors.source_key} />

      {mutation.isError && (
        <div className="alert" role="alert">
          {describeError(mutation.error)}
        </div>
      )}

      <button type="submit" disabled={!canSubmit}>
        {mutation.isPending ? "Submitting…" : "Run job"}
      </button>
    </form>
  );
}

function FieldError({ id, messages }: { id?: string; messages?: string[] }) {
  if (!messages?.length) return null;
  return (
    <p id={id} className="field-error">
      {messages.join(" ")}
    </p>
  );
}
