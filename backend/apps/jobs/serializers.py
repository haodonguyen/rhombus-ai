from typing import Any

from rest_framework import serializers

from apps.jobs.models import Job, TransformType
from processing.errors import InvalidPatternError
from processing.file_types import FileType
from processing.regex_safety import MAX_PATTERN_LENGTH, check_syntax


class JobCreateSerializer(serializers.Serializer):
    """A job submission. Which of the optional fields apply depends on `transform_type`:

    - regex_replace: exactly one of `nl_prompt` or `pattern`, plus `replacement_value`.
    - normalize_format: `nl_prompt` describing the target format.
    - mask_pii: nothing else; the LLM classifies the target columns from sample values.
    """

    transform_type = serializers.ChoiceField(
        choices=TransformType.choices, required=False, default=TransformType.REGEX_REPLACE
    )
    source_key = serializers.CharField(max_length=1024)
    target_columns = serializers.ListField(
        child=serializers.CharField(max_length=255, trim_whitespace=False),
        min_length=1,
        max_length=50,
    )
    nl_prompt = serializers.CharField(max_length=2000, required=False, default="", allow_blank=True)
    pattern = serializers.CharField(
        max_length=MAX_PATTERN_LENGTH,
        required=False,
        default="",
        allow_blank=True,
        trim_whitespace=False,
    )
    replacement_value = serializers.CharField(
        max_length=1000, required=False, default="", allow_blank=True, trim_whitespace=False
    )

    def validate_source_key(self, value: str) -> str:
        if FileType.from_key(value) is None:
            raise serializers.ValidationError("Only .csv and .xlsx files are supported.")
        return value

    def validate_target_columns(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    def validate_pattern(self, value: str) -> str:
        # Cheap syntax checks only; the task runs the full safety validation.
        if value:
            try:
                check_syntax(value)
            except InvalidPatternError as exc:
                raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        transform = attrs["transform_type"]
        has_prompt = bool(attrs["nl_prompt"])
        has_pattern = bool(attrs["pattern"])
        has_replacement = bool(attrs["replacement_value"])

        if transform == TransformType.REGEX_REPLACE:
            if has_prompt == has_pattern:
                message = (
                    "Provide either a description or a regex, not both."
                    if has_prompt
                    else "Describe what to find, or enter a regex."
                )
                raise serializers.ValidationError({"nl_prompt": [message]})
        elif transform == TransformType.NORMALIZE_FORMAT:
            if has_pattern or has_replacement:
                raise serializers.ValidationError(
                    {"pattern": ["Only find-and-replace jobs take a regex or replacement value."]}
                )
            if not has_prompt:
                raise serializers.ValidationError(
                    {"nl_prompt": ["Describe the target format, for example dates as YYYY-MM-DD."]}
                )
        elif has_prompt or has_pattern or has_replacement:
            raise serializers.ValidationError(
                {
                    "transform_type": [
                        "Masking personal data takes no description, regex or replacement value."
                    ]
                }
            )
        return attrs


class JobSerializer(serializers.ModelSerializer):
    error = serializers.SerializerMethodField()
    cancel_requested = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "status",
            "stage",
            "progress",
            "source_key",
            "file_type",
            "target_columns",
            "transform_type",
            "nl_prompt",
            "pattern",
            "pattern_explanation",
            "transform_spec",
            "llm_cached",
            "replacement_value",
            "row_count",
            "matched_count",
            "error",
            "cancel_requested",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_error(self, job: Job) -> dict[str, Any] | None:
        if not job.error_code:
            return None
        return {"code": job.error_code, "message": job.error_message}

    def get_cancel_requested(self, job: Job) -> bool:
        return job.cancel_requested_at is not None


class ResultsQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    # Larger values are clamped to the maximum rather than rejected.
    page_size = serializers.IntegerField(required=False, default=50, min_value=1)


class ResultRowSerializer(serializers.Serializer):
    row_number = serializers.IntegerField()
    matched = serializers.BooleanField()
    values = serializers.ListField(child=serializers.CharField(allow_null=True))


class ResultsPageSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField())
    rows = ResultRowSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_rows = serializers.IntegerField()
    total_pages = serializers.IntegerField()
