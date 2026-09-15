"""Django settings. Every deployment-specific value comes from environment variables."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.files",
    "apps.jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis DB layout: 0 = Celery broker, 1 = Celery results, 2 = application cache.
REDIS_URL = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "config.exception_handler.api_exception_handler",
}

# --- Celery ---------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_RESULT_EXPIRES = env.int("CELERY_RESULT_EXPIRES", default=60 * 60 * 24)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_SEND_TASK_EVENTS = True
# Spark jobs are heavy: never let one worker process reserve extra tasks.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=60 * 60)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=60 * 65)

# --- Storage ----------------------------------------------------------------
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default=None)
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default=None)
AWS_REGION = env("AWS_REGION", default="us-east-1")
S3_BUCKET = env("S3_BUCKET")
# Set only for S3-compatible stores (MinIO in dev); empty means real AWS S3.
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default=None) or None
RESULTS_PATH = env("RESULTS_PATH", default="/data/results")

# --- Spark ------------------------------------------------------------------
SPARK_MASTER = env("SPARK_MASTER", default="local[*]")
SPARK_DRIVER_MEMORY = env("SPARK_DRIVER_MEMORY", default="2g")
SPARK_SHUFFLE_PARTITIONS = env.int("SPARK_SHUFFLE_PARTITIONS", default=8)
# 16 MiB input partitions: a 270 MiB CSV becomes ~17 tasks instead of 8 on an 8-core
# worker, which spreads work more evenly and makes task-based progress less coarse.
SPARK_MAX_PARTITION_BYTES = env("SPARK_MAX_PARTITION_BYTES", default="16m")
SPARK_JARS_DIR = env("SPARK_JARS_DIR", default=None)

# --- LLM ----------------------------------------------------------------------
# Local Ollama server. An empty LLM_BASE_URL disables natural-language patterns; raw
# regex jobs still work.
LLM_BASE_URL = env("LLM_BASE_URL", default="")
LLM_MODEL = env("LLM_MODEL", default="qwen2.5-coder:3b")
LLM_CACHE_TTL = env.int("LLM_CACHE_TTL", default=60 * 60 * 24 * 7)
# Generous: a request that finds the model unloaded runs slowly while it loads (measured
# 135 s on an 8-core CPU), and timing it out would only restart the load on retry.
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=300.0)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
