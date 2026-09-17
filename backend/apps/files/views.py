from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.files import connections, services
from apps.files.serializers import (
    ConnectedSerializer,
    FileListQuerySerializer,
    FilePageSerializer,
    FilePreviewQuerySerializer,
    FilePreviewSerializer,
    S3ConnectionSerializer,
)


class S3ConnectionView(APIView):
    """Exchange an access key and secret key for a short-lived connection id."""

    def post(self, request: Request) -> Response:
        payload = S3ConnectionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        connection = connections.S3Connection(
            bucket=payload.validated_data["bucket"],
            region=payload.validated_data["region"],
            access_key_id=payload.validated_data["access_key_id"],
            secret_access_key=payload.validated_data["secret_access_key"],
            endpoint_url=payload.validated_data["endpoint_url"],
        )
        services.verify(connection)
        connection_id = connections.store(connection)
        body = {
            "connection_id": connection_id,
            "bucket": connection.bucket,
            "region": connection.region,
            "demo": False,
            "expires_in": settings.S3_CONNECTION_TTL,
        }
        return Response(ConnectedSerializer(body).data, status=status.HTTP_201_CREATED)


class S3DemoConnectionView(APIView):
    """The bucket this deployment offers for trying the app without AWS credentials."""

    def get(self, request: Request) -> Response:
        demo = connections.demo_connection()
        if demo is None:
            return Response({"available": False})
        body = {
            "connection_id": connections.DEMO_CONNECTION_ID,
            "bucket": demo.bucket,
            "region": demo.region,
            "demo": True,
            "expires_in": 0,
        }
        return Response({"available": True, **ConnectedSerializer(body).data})


class FileListView(APIView):
    """List CSV/XLSX files in the connected bucket, paginated by cursor."""

    def get(self, request: Request) -> Response:
        params = FileListQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        connection = connections.load(params.validated_data["connection_id"])
        page = services.list_files(
            connection,
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
        connection = connections.load(params.validated_data["connection_id"])
        preview = services.get_file_preview(connection, params.validated_data["key"])
        return Response(FilePreviewSerializer(preview).data)
