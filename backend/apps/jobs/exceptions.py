from apps.core.exceptions import ConflictError, DomainError, NotFoundError


class JobNotFound(NotFoundError):
    code = "JOB_NOT_FOUND"
    default_message = "The requested job was not found."


class InvalidJobRequest(DomainError):
    code = "VALIDATION_ERROR"
    default_message = "The request contains invalid fields."


class JobNotReady(ConflictError):
    code = "JOB_NOT_READY"
    default_message = "Results are available only after the job has succeeded."


class ResultsUnavailable(DomainError):
    code = "RESULTS_UNAVAILABLE"
    http_status = 410
    default_message = "Results for this job are no longer available."
