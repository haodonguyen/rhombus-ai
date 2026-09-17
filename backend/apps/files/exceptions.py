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


class S3CredentialsInvalid(DomainError):
    code = "S3_CREDENTIALS_INVALID"
    default_message = "S3 rejected these credentials. Check the access key and secret key."


class S3BucketNotFound(NotFoundError):
    code = "S3_BUCKET_NOT_FOUND"
    default_message = "That bucket does not exist, or these credentials cannot see it."


class S3ConnectionExpired(DomainError):
    code = "S3_CONNECTION_EXPIRED"
    default_message = "The S3 connection has expired. Connect again to continue."
