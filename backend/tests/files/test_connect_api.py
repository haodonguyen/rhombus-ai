"""The connect endpoint: credentials in, an opaque connection id out."""

import pytest
from botocore.exceptions import ClientError

from apps.files import services
from tests.conftest import TEST_BUCKET

pytestmark = pytest.mark.django_db

CREDENTIALS = {
    "access_key_id": "AKIAEXAMPLE",
    "secret_access_key": "secret-value",
    "bucket": TEST_BUCKET,
    "region": "us-east-1",
}


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "ListObjectsV2")


def test_valid_credentials_return_a_connection_id(api_client, s3):
    response = api_client.post("/api/s3/connections/", CREDENTIALS, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["bucket"] == TEST_BUCKET
    assert body["demo"] is False
    assert body["expires_in"] > 0
    assert body["connection_id"]


def test_response_never_echoes_the_credentials(api_client, s3):
    body = api_client.post("/api/s3/connections/", CREDENTIALS, format="json").content.decode()

    assert "secret-value" not in body
    assert "AKIAEXAMPLE" not in body


def test_the_returned_id_can_list_that_bucket(api_client, s3):
    s3.put_object(Bucket=TEST_BUCKET, Key="a.csv", Body=b"ID\n1\n")
    connection_id = api_client.post("/api/s3/connections/", CREDENTIALS, format="json").json()[
        "connection_id"
    ]

    response = api_client.get("/api/files/", {"connection_id": connection_id})

    assert response.status_code == 200
    assert [f["key"] for f in response.json()["files"]] == ["a.csv"]


@pytest.mark.parametrize(
    ("code", "status", "error"),
    [
        ("InvalidAccessKeyId", 400, "S3_CREDENTIALS_INVALID"),
        ("SignatureDoesNotMatch", 400, "S3_CREDENTIALS_INVALID"),
        ("AccessDenied", 400, "S3_CREDENTIALS_INVALID"),
        ("NoSuchBucket", 404, "S3_BUCKET_NOT_FOUND"),
    ],
)
def test_rejected_credentials_map_to_clear_errors(api_client, monkeypatch, code, status, error):
    class Rejecting:
        def list_objects_v2(self, **kwargs):
            raise client_error(code)

    monkeypatch.setattr(services, "get_s3_client", lambda connection: Rejecting())

    response = api_client.post("/api/s3/connections/", CREDENTIALS, format="json")

    assert response.status_code == status
    assert response.json()["error"]["code"] == error


def test_missing_fields_are_validation_errors(api_client):
    response = api_client.post("/api/s3/connections/", {"bucket": TEST_BUCKET}, format="json")

    assert response.status_code == 400
    assert set(response.json()["error"]["details"]) == {"access_key_id", "secret_access_key"}


def test_an_expired_connection_id_is_reported(api_client, s3):
    response = api_client.get("/api/files/", {"connection_id": "no-longer-stored"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "S3_CONNECTION_EXPIRED"


def test_demo_endpoint_advertises_the_configured_bucket(api_client, settings):
    settings.S3_DEMO_ENABLED = True
    settings.S3_BUCKET = TEST_BUCKET

    body = api_client.get("/api/s3/connections/demo/").json()

    assert body["available"] is True
    assert (body["connection_id"], body["bucket"], body["demo"]) == ("demo", TEST_BUCKET, True)


def test_demo_endpoint_reports_when_disabled(api_client, settings):
    settings.S3_DEMO_ENABLED = False

    assert api_client.get("/api/s3/connections/demo/").json() == {"available": False}
