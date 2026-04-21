from picsure._dev.redaction import redact_for_log, redact_headers


def test_redact_headers_masks_authorization():
    headers = {
        "Authorization": "Bearer secret-abc123",
        "Content-Type": "application/json",
    }
    out = redact_headers(headers)
    assert out["Authorization"] == "Bearer ***"
    assert out["Content-Type"] == "application/json"


def test_redact_headers_case_insensitive():
    headers = {"authorization": "Bearer x"}
    out = redact_headers(headers)
    assert out["authorization"] == "Bearer ***"


def test_redact_headers_preserves_when_no_auth():
    headers = {"Content-Type": "application/json"}
    assert redact_headers(headers) == headers


def test_redact_search_body_is_preserved():
    body = {"query": "blood pressure", "searchQueryType": "ALL"}
    out = redact_for_log("/picsure/search/abc", "POST", body)
    assert out is not None
    assert "blood pressure" in out


def test_redact_psama_body_strips_email():
    body = {"email": "user@example.com", "expirationDate": "2026-06-15"}
    out = redact_for_log("/psama/user/me", "GET", body)
    assert out is not None
    assert "user@example.com" not in out
    assert "***" in out


def test_redact_participant_query_returns_none():
    body = {"query": {"expectedResultType": "DATAFRAME", "fields": []}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is None


def test_redact_timestamp_query_returns_none():
    body = {"query": {"expectedResultType": "DATAFRAME_TIMESERIES", "fields": []}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is None


def test_redact_count_query_is_preserved():
    body = {"query": {"expectedResultType": "COUNT", "fields": []}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is not None
    assert "COUNT" in out


def test_redact_empty_body_returns_empty_string():
    out = redact_for_log("/picsure/search/abc", "POST", None)
    assert out == ""


def test_redact_pfb_export_returns_none():
    body = {"query": {"expectedResultType": "DATAFRAME_PFB"}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is None


def test_redact_info_resources_is_preserved():
    body = {"uuid-1": "hpds"}
    out = redact_for_log("/picsure/info/resources", "GET", body)
    assert out is not None
    assert "hpds" in out
