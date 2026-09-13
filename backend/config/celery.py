"""Celery application. Configuration is read from Django settings (CELERY_* keys)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("nl_regex")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
