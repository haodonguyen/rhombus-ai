from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core import health as health_checks


@api_view(["GET"])
def health(request: Request) -> Response:
    """Report reachability of the database and Redis; 503 if any dependency is down."""
    checks = health_checks.run_health_checks()
    healthy = all(result == health_checks.OK for result in checks.values())
    return Response(
        {"status": "ok" if healthy else "degraded", **checks},
        status=200 if healthy else 503,
    )
