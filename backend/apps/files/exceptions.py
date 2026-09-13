from apps.core.exceptions import DomainError, NotFoundError, ServiceUnavailableError


class StoredFileNotFound(NotFoundError):
    code = "FILE_NOT_FOUND"
    default_message = "The requested file was not found."


class UnsupportedFileType(DomainError):
    code = "UNSUPPORTED_FILE_TYPE"
    default_message = "Only CSV (.csv) and Excel (.xlsx) files are supported."


class PreviewUnavailable(DomainError):
    code = "PREVIEW_UNAVAILABLE"
    http_status = 422
    default_message = "A preview is not available for this file."


class StorageUnavailable(ServiceUnavailableError):
    code = "STORAGE_UNAVAILABLE"
    default_message = "File storage is unavailable. Please retry shortly."
