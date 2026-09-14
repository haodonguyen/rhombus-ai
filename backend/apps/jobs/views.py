from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs import services
from apps.jobs.serializers import (
    JobCreateSerializer,
    JobSerializer,
    ResultsPageSerializer,
    ResultsQuerySerializer,
)


class JobCreateView(APIView):
    """Submit a job. Returns 202 immediately; the work runs in a Celery worker."""

    def post(self, request: Request) -> Response:
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.submit_job(services.JobRequest(**serializer.validated_data))
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class JobDetailView(APIView):
    def get(self, request: Request, job_id: UUID) -> Response:
        return Response(JobSerializer(services.get_job(job_id)).data)


class JobCancelView(APIView):
    """Cancel a queued or running job. 202: running jobs stop asynchronously."""

    def post(self, request: Request, job_id: UUID) -> Response:
        job = services.cancel_job(job_id)
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class JobResultsView(APIView):
    def get(self, request: Request, job_id: UUID) -> Response:
        params = ResultsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = services.get_job_results(job_id, **params.validated_data)
        return Response(ResultsPageSerializer(page).data)
