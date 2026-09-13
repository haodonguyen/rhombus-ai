from rest_framework import serializers


class FileListQuerySerializer(serializers.Serializer):
    prefix = serializers.CharField(required=False, default="", allow_blank=True, max_length=1024)
    cursor = serializers.CharField(required=False, default=None, allow_blank=True, max_length=1024)
    page_size = serializers.IntegerField(required=False, default=100, min_value=1, max_value=1000)


class StoredFileSerializer(serializers.Serializer):
    key = serializers.CharField()
    size = serializers.IntegerField()
    last_modified = serializers.DateTimeField()
    file_type = serializers.CharField()


class FilePageSerializer(serializers.Serializer):
    files = StoredFileSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class FilePreviewQuerySerializer(serializers.Serializer):
    key = serializers.CharField(max_length=1024)


class FilePreviewSerializer(serializers.Serializer):
    key = serializers.CharField()
    file_type = serializers.CharField()
    columns = serializers.ListField(child=serializers.CharField())
    sample_rows = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField(allow_null=True))
    )
