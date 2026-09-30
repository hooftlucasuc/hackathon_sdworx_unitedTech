import pytest

from app.signature import SignatureError, sign, verify

SECRET = "wsec_test"
BODY = b'{"type":"post_call_transcription"}'
NOW = 1_790_000_000


def test_valid_signature_passes():
    verify(sign(BODY, SECRET, NOW), BODY, SECRET, now=NOW + 5)


def test_wrong_secret_fails():
    with pytest.raises(SignatureError, match="mismatch"):
        verify(sign(BODY, "other", NOW), BODY, SECRET, now=NOW)


def test_tampered_body_fails():
    with pytest.raises(SignatureError, match="mismatch"):
        verify(sign(BODY, SECRET, NOW), BODY + b" ", SECRET, now=NOW)


def test_expired_signature_fails():
    with pytest.raises(SignatureError, match="expired"):
        verify(sign(BODY, SECRET, NOW), BODY, SECRET, tolerance_secs=1800, now=NOW + 1801)


def test_future_timestamp_fails():
    with pytest.raises(SignatureError, match="future"):
        verify(sign(BODY, SECRET, NOW + 3600), BODY, SECRET, now=NOW)


@pytest.mark.parametrize("header", [None, "", "garbage", "t=abc,v0=00", "t=123", "v0=abc"])
def test_malformed_headers_fail(header):
    with pytest.raises(SignatureError):
        verify(header, BODY, SECRET, now=NOW)


def test_missing_secret_fails_closed():
    with pytest.raises(SignatureError, match="not configured"):
        verify(sign(BODY, SECRET, NOW), BODY, "", now=NOW)
