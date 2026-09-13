import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useId, useState } from "react";

import { describeError, fieldErrors } from "../../api/client";
import { createJob, type Job } from "../../api/jobs";
import { jobQueryKey } from "./useJob";

type PatternMode = "describe" | "regex";

interface JobFormProps {
  sourceKey: string;
  targetColumns: string[];
  onSubmitted: (job: Job) => void;
}

export function JobForm({ sourceKey, targetColumns, onSubmitted }: JobFormProps) {
  const id = useId();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<PatternMode>("describe");
  const [description, setDescription] = useState("");
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
  const trimmedDescription = description.trim();
  const hasPatternInput = mode === "describe" ? trimmedDescription.length > 0 : pattern.length > 0;
  const canSubmit = targetColumns.length > 0 && hasPatternInput && !mutation.isPending;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    const common = {
      source_key: sourceKey,
      target_columns: targetColumns,
      replacement_value: replacement,
    };
    mutation.mutate(
      mode === "describe" ? { ...common, nl_prompt: trimmedDescription } : { ...common, pattern },
    );
  }

  return (
    <form className="job-form" onSubmit={handleSubmit} noValidate>
      {mode === "describe" ? (
        <div className="field">
          <label htmlFor={`${id}-description`}>Describe what to find</label>
          <textarea
            id={`${id}-description`}
            rows={2}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="e.g. email addresses, or phone numbers in any format"
            aria-invalid={errors.nl_prompt ? true : undefined}
            aria-describedby={errors.nl_prompt ? `${id}-description-error` : undefined}
          />
          <FieldError id={`${id}-description-error`} messages={errors.nl_prompt} />
        </div>
      ) : (
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
      )}

      <button
        type="button"
        className="link"
        onClick={() => setMode((current) => (current === "describe" ? "regex" : "describe"))}
      >
        {mode === "describe" ? "Enter a regex instead" : "Describe it in plain English instead"}
      </button>

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
