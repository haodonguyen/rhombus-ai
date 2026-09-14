"""The Spark transformation for each job type, built inside the job's Spark run.

Transforms that need an LLM specification sample the loaded data first, ask the LLM once and
save the specification on the job, so a retried job reuses it instead of asking again.
Imports PySpark, so only the worker process imports this module.
"""

from collections.abc import Callable
from typing import TypeVar

from pyspark.sql import DataFrame

from apps.jobs.cancellation import raise_if_cancel_requested
from apps.jobs.models import Job, TransformType
from apps.llm.service import (
    GeneratedSpec,
    classify_pii,
    generate_normalization,
    normalization_spec_from_suggestion,
    pii_spec_from_suggestion,
)
from processing.pipeline import Builder
from processing.progress import ProgressTracker
from processing.sampling import sample_column_values
from processing.transforms.mask_pii import mask_pii
from processing.transforms.normalize import normalize_format
from processing.transforms.regex_replace import regex_replace

SpecT = TypeVar("SpecT")

SPEC_STAGE = "GENERATING_SPEC"


def builder_for(job: Job, *, pattern: str | None, progress: ProgressTracker) -> Builder:
    columns = tuple(job.target_columns)

    if job.transform_type == TransformType.REGEX_REPLACE:
        if pattern is None:
            raise ValueError("A find-and-replace job needs its pattern resolved first.")
        return lambda df: regex_replace(df, columns, pattern, job.replacement_value)

    if job.transform_type == TransformType.NORMALIZE_FORMAT:

        def build_normalization(df: DataFrame) -> DataFrame:
            if job.transform_spec:
                spec = normalization_spec_from_suggestion(job.transform_spec)
            else:
                spec = _generate_spec(
                    job,
                    progress,
                    sample=lambda: sample_column_values(df, columns),
                    generate=lambda samples: generate_normalization(job.nl_prompt, samples),
                )
            return normalize_format(df, columns, spec)

        return build_normalization

    if job.transform_type == TransformType.MASK_PII:

        def build_masking(df: DataFrame) -> DataFrame:
            if job.transform_spec:
                spec = pii_spec_from_suggestion(job.transform_spec, columns)
            else:
                spec = _generate_spec(
                    job,
                    progress,
                    sample=lambda: sample_column_values(df, columns),
                    generate=classify_pii,
                )
            return mask_pii(df, spec)

        return build_masking

    raise ValueError(f"Unsupported transform type: {job.transform_type}")


def _generate_spec(
    job: Job,
    progress: ProgressTracker,
    *,
    sample: Callable[[], dict[str, list[str]]],
    generate: Callable[[dict[str, list[str]]], GeneratedSpec[SpecT]],
) -> SpecT:
    samples = sample()
    raise_if_cancel_requested(job.id)
    progress.enter_stage(SPEC_STAGE)
    generated = generate(samples)
    Job.objects.filter(pk=job.id).update(
        transform_spec=generated.suggestion,
        pattern_explanation=generated.explanation,
        llm_cached=generated.cached,
    )
    raise_if_cancel_requested(job.id)
    return generated.spec
