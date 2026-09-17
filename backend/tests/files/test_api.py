import io

from botocore.exceptions import EndpointConnectionError
from openpyxl import Workbook

from apps.files import services
from tests.conftest import TEST_BUCKET

CSV_CONTENT = "ID,Name,Email\n" + "".join(
    f"{i},Person {i},person{i}@example.com\n" for i in range(1, 16)
)


def list_files(api_client, connection: str, **params):
    return api_client.get("/api/files/", {"connection_id": connection, **params})


def preview(api_client, connection: str, **params):
    return api_client.get("/api/files/columns/", {"connection_id": connection, **params})


def put(s3, key: str, body: bytes) -> None:
    s3.put_object(Bucket=TEST_BUCKET, Key=key, Body=body)


def xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --- listing ------------------------------------------------------------------------


def test_lists_only_supported_files_in_key_order(api_client, s3, s3_connection):
    put(s3, "b.xlsx", b"x")
    put(s3, "a.csv", b"x")
    put(s3, "notes.txt", b"x")
    put(s3, "folder/", b"")

    response = list_files(api_client, s3_connection)

    assert response.status_code == 200
    body = response.json()
    assert [(f["key"], f["file_type"]) for f in body["files"]] == [
        ("a.csv", "csv"),
        ("b.xlsx", "xlsx"),
    ]
    assert body["next_cursor"] is None


def test_pagination_skips_unsupported_objects_with_cursor(api_client, s3, s3_connection):
    for key in ["1.csv", "2.txt", "3.csv", "4.txt", "5.xlsx"]:
        put(s3, key, b"x")

    first = list_files(api_client, s3_connection, page_size=2).json()
    second = list_files(api_client, s3_connection, page_size=2, cursor=first["next_cursor"]).json()

    assert [f["key"] for f in first["files"]] == ["1.csv", "3.csv"]
    assert first["next_cursor"] == "3.csv"
    assert [f["key"] for f in second["files"]] == ["5.xlsx"]
    assert second["next_cursor"] is None


def test_empty_bucket_returns_empty_page(api_client, s3, s3_connection):
    response = list_files(api_client, s3_connection)

    assert response.status_code == 200
    assert response.json() == {"files": [], "next_cursor": None}


def test_storage_failure_returns_503(api_client, s3, s3_connection, monkeypatch):
    class UnreachableClient:
        def list_objects_v2(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="http://minio:9000")

    monkeypatch.setattr(services, "get_s3_client", lambda connection: UnreachableClient())

    response = list_files(api_client, s3_connection)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"


def test_invalid_page_size_is_a_validation_error(api_client, s3, s3_connection):
    response = list_files(api_client, s3_connection, page_size=0)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "page_size" in response.json()["error"]["details"]


# --- preview ------------------------------------------------------------------------


def test_csv_preview_returns_columns_and_ten_sample_rows(api_client, s3, s3_connection):
    put(s3, "people.csv", CSV_CONTENT.encode())

    response = preview(api_client, s3_connection, key="people.csv")

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["ID", "Name", "Email"]
    assert len(body["sample_rows"]) == 10
    assert body["sample_rows"][0] == ["1", "Person 1", "person1@example.com"]


def test_csv_preview_drops_partial_last_line_when_truncated(
    api_client, s3, s3_connection, monkeypatch
):
    put(s3, "people.csv", CSV_CONTENT.encode())
    # Cut the byte range in the middle of the second data row.
    cutoff = CSV_CONTENT.index("2,Person 2") + 5
    monkeypatch.setattr(services, "CSV_PREVIEW_BYTES", cutoff)

    body = preview(api_client, s3_connection, key="people.csv").json()

    assert body["sample_rows"] == [["1", "Person 1", "person1@example.com"]]


def test_xlsx_preview_uses_first_sheet(api_client, s3, s3_connection):
    put(s3, "people.xlsx", xlsx_bytes([["ID", "Email"], [1, "a@example.com"], [2, None]]))

    body = preview(api_client, s3_connection, key="people.xlsx").json()

    assert body["columns"] == ["ID", "Email"]
    assert body["sample_rows"] == [["1", "a@example.com"], ["2", None]]


def test_empty_file_preview_has_no_columns(api_client, s3, s3_connection):
    put(s3, "empty.csv", b"")

    body = preview(api_client, s3_connection, key="empty.csv").json()

    assert body["columns"] == []
    assert body["sample_rows"] == []


def test_preview_unknown_key_returns_404(api_client, s3, s3_connection):
    response = preview(api_client, s3_connection, key="missing.csv")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_preview_unsupported_type_returns_400(api_client, s3, s3_connection):
    response = preview(api_client, s3_connection, key="notes.txt")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_preview_requires_key(api_client, s3, s3_connection):
    response = api_client.get("/api/files/columns/", {"connection_id": s3_connection})

    assert response.status_code == 400
    assert response.json()["error"]["details"]["key"]
