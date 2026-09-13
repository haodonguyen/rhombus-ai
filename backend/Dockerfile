# syntax=docker/dockerfile:1
# Targets: `web` (Django API, Flower, seeding) and `worker` (Celery + PySpark + Java).

FROM python:3.11-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd --system app \
    && useradd --system --gid app --create-home app \
    && mkdir -p /data/results \
    && chown app:app /data/results
WORKDIR /app
COPY requirements/base.txt requirements/dev.txt requirements/
RUN pip install -r requirements/base.txt -r requirements/dev.txt


FROM base AS web
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]


FROM base AS worker
RUN mkdir -p /usr/share/man/man1 \
    && apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")" /opt/java
ENV JAVA_HOME=/opt/java \
    SPARK_JARS_DIR=/opt/spark-jars
COPY requirements/worker.txt requirements/
RUN pip install -r requirements/worker.txt
COPY docker/fetch_spark_jars.py /tmp/fetch_spark_jars.py
RUN python /tmp/fetch_spark_jars.py "$SPARK_JARS_DIR" && rm /tmp/fetch_spark_jars.py
COPY --chown=app:app . .
USER app
CMD ["celery", "-A", "config", "worker", "--loglevel=info", "--concurrency=1", "--events"]
