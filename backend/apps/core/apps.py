from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Cross-cutting infrastructure: health checks and environment smoke tasks."""

    name = "apps.core"
    label = "core"
