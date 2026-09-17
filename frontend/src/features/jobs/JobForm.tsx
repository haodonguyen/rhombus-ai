import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useId, useState } from "react";

import { describeError, fieldErrors } from "../../api/client";
import { FieldError } from "../../components/FieldError";
import { type CreateJob, createJob, type Job, type TransformType } from "../../api/jobs";
import { jobQueryKey } from "./useJob";

type PatternMode = "describe" | "regex";

const TRANSFORMS: { value: TransformType; label: string; hint: string }[] = [
  {
    value: "regex_replace",
    label: "Find & replace",
    hint: "Replace text that matches a pattern.",
  },
  {
    value: "normalize_format",
    label: "Normalize format",
    hint: "Rewrite values such as dates or phone numbers into one consistent format.",
  },
  {
    value: "mask_pii",
    label: "Mask personal data",
    hint: "The model finds names, emails, phone numbers and other personal data in sample values; the job masks them.",
  },
];

interface JobFormProps {
  connectionId: string;
  sourceKey: string;
  targetColumns: string[];
  onSubmitted: (job: Job) => void;
}

export function JobForm({ connectionId, sourceKey, targetColumns, onSubmitted }: JobFormProps) {
  const id = useId();
  const queryClient = useQueryClient();
  const [transform, setTransform] = useState<TransformType>("regex_replace");
  const [mode, setMode] = useState<PatternMode>("describe");
  const [description, setDescription] = useState("");
  const [targetFormat, setTargetFormat] = useState("");
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
  const payload = buildPayload();
  const canSubmit = targetColumns.length > 0 && payload !== null && !mutation.isPending;

  /** The request for the chosen transformation, or null while required input is missing. */
  function buildPayload(): CreateJob | null {
    const target = {
      connection_id: connectionId,
      source_key: sourceKey,
      target_columns: targetColumns,
    };
    switch (transform) {
      case "regex_replace": {
        const common = { ...target, transform_type: transform, replacement_value: replacement };
        if (mode === "describe") {
          const text = description.trim();
          return text ? { ...common, nl_prompt: text } : null;
        }
        return pattern ? { ...common, pattern } : null;
      }
      case "normalize_format": {
        const text = targetFormat.trim();
        return text ? { ...target, transform_type: transform, nl_prompt: text } : null;
      }
      case "mask_pii":
        return { ...target, transform_type: transform };
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || payload === null) return;
    mutation.mutate(payload);
  }

  return (
    <form className="job-form" onSubmit={handleSubmit} noValidate>
      <fieldset className="transform-options">
        <legend>Transformation</legend>
        {TRANSFORMS.map((option) => (
          <label
            key={option.value}
            className="transform-option"
            data-selected={option.value === transform}
          >
            <input
              type="radio"
              name={`${id}-transform`}
              value={option.value}
              checked={option.value === transform}
              onChange={() => setTransform(option.value)}
            />
            <span>
              <strong>{option.label}</strong>
              <span className="muted">{option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <FieldError messages={errors.transform_type} />

      {transform === "regex_replace" && (
        <>
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
        </>
      )}

      {transform === "normalize_format" && (
        <div className="field">
          <label htmlFor={`${id}-format`}>Target format</label>
          <textarea
            id={`${id}-format`}
            rows={2}
            value={targetFormat}
            onChange={(event) => setTargetFormat(event.target.value)}
            placeholder="e.g. dates as YYYY-MM-DD, or phone numbers like 555-123-4567"
            aria-invalid={errors.nl_prompt ? true : undefined}
            aria-describedby={errors.nl_prompt ? `${id}-format-error` : undefined}
          />
          <FieldError id={`${id}-format-error`} messages={errors.nl_prompt} />
          <FieldError messages={errors.pattern} />
        </div>
      )}

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
