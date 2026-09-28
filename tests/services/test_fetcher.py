from unittest.mock import MagicMock, patch

from backend.app.services.sanctions.fetcher import fetch_with_conditional_get


def _mock_response(status_code: int, content: bytes = b"", headers: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    return resp


@patch("backend.app.services.sanctions.fetcher.httpx.Client")
def test_304_short_circuits_as_not_modified(mock_client_cls):
    mock_client = MagicMock()
    mock_client.get.return_value = _mock_response(304)
    mock_client_cls.return_value.__enter__.return_value = mock_client

    result = fetch_with_conditional_get(
        "https://example.test/sdn.xml",
        previous_etag="abc",
        previous_last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        previous_sha256="deadbeef",
    )
    assert result.status == "not_modified"
    assert result.sha256 == "deadbeef"


@patch("backend.app.services.sanctions.fetcher.httpx.Client")
def test_200_with_identical_sha_is_unchanged(mock_client_cls):
    body = b"<sdnList></sdnList>"
    import hashlib

    sha = hashlib.sha256(body).hexdigest()

    mock_client = MagicMock()
    mock_client.get.return_value = _mock_response(200, content=body)
    mock_client_cls.return_value.__enter__.return_value = mock_client

    result = fetch_with_conditional_get(
        "https://example.test/sdn.xml",
        previous_etag=None,
        previous_last_modified=None,
        previous_sha256=sha,
    )
    assert result.status == "unchanged"


@patch("backend.app.services.sanctions.fetcher.httpx.Client")
def test_200_with_new_content_is_fetched(mock_client_cls):
    body = b"<sdnList>new content</sdnList>"
    mock_client = MagicMock()
    mock_client.get.return_value = _mock_response(
        200,
        content=body,
        headers={"etag": '"xyz"', "last-modified": "Tue, 02 Jan 2026 00:00:00 GMT"},
    )
    mock_client_cls.return_value.__enter__.return_value = mock_client

    result = fetch_with_conditional_get(
        "https://example.test/sdn.xml",
        previous_etag="old-etag",
        previous_last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        previous_sha256="different-sha",
    )
    assert result.status == "fetched"
    assert result.body == body
    assert result.etag == '"xyz"'


@patch("backend.app.services.sanctions.fetcher.httpx.Client")
def test_conditional_headers_sent_when_previous_values_present(mock_client_cls):
    mock_client = MagicMock()
    mock_client.get.return_value = _mock_response(304)
    mock_client_cls.return_value.__enter__.return_value = mock_client

    fetch_with_conditional_get(
        "https://example.test/sdn.xml",
        previous_etag="abc",
        previous_last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        previous_sha256="deadbeef",
    )
    _, kwargs = mock_client.get.call_args
    assert kwargs["headers"]["If-None-Match"] == "abc"
    assert kwargs["headers"]["If-Modified-Since"] == "Mon, 01 Jan 2026 00:00:00 GMT"
