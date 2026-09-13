from enum import StrEnum
from pathlib import PurePosixPath


class FileType(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"

    @classmethod
    def from_key(cls, key: str) -> "FileType | None":
        """Detect the file type from an object key's extension; None if unsupported."""
        extension = PurePosixPath(key).suffix.lower().lstrip(".")
        try:
            return cls(extension)
        except ValueError:
            return None
