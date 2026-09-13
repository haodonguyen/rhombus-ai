from typing import Any

from rest_framework import serializers

from apps.jobs.models import Job
from processing.errors import InvalidPatternError
from processing.file_types import FileType
from processing.regex_safety import MAX_PATTERN_LENGTH, check_syntax


class RegexReplaceJobCreateSerializer(serializers.Serializer):
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
        if bool(attrs["nl_prompt"]) == bool(attrs["pattern"]):
            message = (
                "Provide either a description or a regex, not both."
                if attrs["nl_prompt"]
                else "Describe what to find, or enter a regex."
            )
            raise serializers.ValidationError({"nl_prompt": [message]})
        return attrs


class JobSerializer(serializers.ModelSerializer):
    error = serializers.SerializerMethodField()

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
            "llm_cached",
            "replacement_value",
            "row_count",
            "matched_count",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_error(self, job: Job) -> dict[str, Any] | None:
        if not job.error_code:
            return None
        return {"code": job.error_code, "message": job.error_message}


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
