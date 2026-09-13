from processing.file_types import FileType
from processing.schema import find_missing_columns


def test_find_missing_columns_preserves_request_order():
    assert find_missing_columns(["A", "B"], ["C", "A", "D"]) == ["C", "D"]


def test_reserved_columns_are_never_available():
    assert find_missing_columns(["__row_id", "A"], ["__row_id"]) == ["__row_id"]


def test_file_type_from_key():
    assert FileType.from_key("dir/data.CSV") is FileType.CSV
    assert FileType.from_key("data.xlsx") is FileType.XLSX
    assert FileType.from_key("data.xls") is None
    assert FileType.from_key("folder/") is None
