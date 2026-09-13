from django.apps import AppConfig


class JobsConfig(AppConfig):
    """Asynchronous data transformation jobs: submission, execution and results."""

    name = "apps.jobs"
    label = "jobs"
