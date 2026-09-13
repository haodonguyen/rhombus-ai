from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.files import services
from apps.files.serializers import (
    FileListQuerySerializer,
    FilePageSerializer,
    FilePreviewQuerySerializer,
    FilePreviewSerializer,
)


class FileListView(APIView):
    """List CSV/XLSX files in the bucket, paginated by cursor."""

    def get(self, request: Request) -> Response:
        params = FileListQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = services.list_files(
            prefix=params.validated_data["prefix"],
            cursor=params.validated_data["cursor"] or None,
            page_size=params.validated_data["page_size"],
        )
        return Response(FilePageSerializer(page).data)


class FilePreviewView(APIView):
    """Column names and a few sample rows, used to pick target columns."""

    def get(self, request: Request) -> Response:
        params = FilePreviewQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        preview = services.get_file_preview(params.validated_data["key"])
        return Response(FilePreviewSerializer(preview).data)
