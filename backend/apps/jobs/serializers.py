import re
from typing import Any

from rest_framework import serializers

from apps.jobs.models import Job
from processing.file_types import FileType


class RegexReplaceJobCreateSerializer(serializers.Serializer):
    source_key = serializers.CharField(max_length=1024)
    target_columns = serializers.ListField(
        child=serializers.CharField(max_length=255, trim_whitespace=False),
        min_length=1,
        max_length=50,
    )
    pattern = serializers.CharField(max_length=500, trim_whitespace=False)
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
        # A basic syntax check; Spark re-validates against the Java regex engine.
        try:
            re.compile(value)
        except re.error as exc:
            raise serializers.ValidationError(f"Invalid regular expression: {exc}") from exc
        return value


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
            "pattern",
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
