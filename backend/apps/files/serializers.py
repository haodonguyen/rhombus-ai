from rest_framework import serializers


class S3ConnectionSerializer(serializers.Serializer):
    """Credentials for one bucket. Write-only: nothing here is ever sent back."""

    access_key_id = serializers.CharField(max_length=128, trim_whitespace=True)
    secret_access_key = serializers.CharField(max_length=256, trim_whitespace=True)
    bucket = serializers.CharField(max_length=255, trim_whitespace=True)
    region = serializers.CharField(
        max_length=64, required=False, default="us-east-1", allow_blank=True
    )
    # Set only for S3-compatible storage such as MinIO; blank means Amazon S3.
    endpoint_url = serializers.URLField(required=False, default="", allow_blank=True)


class ConnectedSerializer(serializers.Serializer):
    connection_id = serializers.CharField()
    bucket = serializers.CharField()
    region = serializers.CharField()
    demo = serializers.BooleanField()
    expires_in = serializers.IntegerField()


class FileListQuerySerializer(serializers.Serializer):
    connection_id = serializers.CharField(max_length=64)
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
    connection_id = serializers.CharField(max_length=64)
    key = serializers.CharField(max_length=1024)


class FilePreviewSerializer(serializers.Serializer):
    key = serializers.CharField()
    file_type = serializers.CharField()
    columns = serializers.ListField(child=serializers.CharField())
    sample_rows = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField(allow_null=True))
    )
