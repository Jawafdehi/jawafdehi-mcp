"""Tests for Open WebUI signed-JWT identity extraction in the HTTP server.

When OWUI_USER_JWT_SECRET is set, the server trusts only the HS256
X-OpenWebUI-User-Jwt that stock Open WebUI mints; the legacy plaintext
X-Jawafdehi-User-* headers are spoofable and ignored. Without the secret it
falls back to the legacy headers (local dev).
"""

import time

import jwt

from jawafdehi_mcp.http_server import extract_identity

SECRET = "shared-test-secret"


def _mint_owui_jwt(
    secret, *, sub="owui-cw-1", name="caseworker1", issuer="open-webui", expires_in=300
):
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": f"{sub}@example.com",
        "name": name,
        "role": "user",
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_jwt_yields_identity(monkeypatch):
    monkeypatch.setenv("OWUI_USER_JWT_SECRET", SECRET)
    token = _mint_owui_jwt(SECRET, sub="owui-cw-1", name="caseworker1")
    uid, uname = extract_identity({b"x-openwebui-user-jwt": token.encode()})
    assert uid == "owui-cw-1"
    assert uname == "caseworker1"


def test_wrong_secret_rejected(monkeypatch):
    monkeypatch.setenv("OWUI_USER_JWT_SECRET", SECRET)
    token = _mint_owui_jwt("a-different-secret")
    uid, uname = extract_identity({b"x-openwebui-user-jwt": token.encode()})
    assert uid is None and uname is None


def test_expired_jwt_rejected(monkeypatch):
    monkeypatch.setenv("OWUI_USER_JWT_SECRET", SECRET)
    token = _mint_owui_jwt(SECRET, expires_in=-10)
    uid, _ = extract_identity({b"x-openwebui-user-jwt": token.encode()})
    assert uid is None


def test_wrong_issuer_rejected(monkeypatch):
    monkeypatch.setenv("OWUI_USER_JWT_SECRET", SECRET)
    token = _mint_owui_jwt(SECRET, issuer="evil")
    uid, _ = extract_identity({b"x-openwebui-user-jwt": token.encode()})
    assert uid is None


def test_missing_jwt_with_secret_set(monkeypatch):
    monkeypatch.setenv("OWUI_USER_JWT_SECRET", SECRET)
    uid, _ = extract_identity({})
    assert uid is None


def test_legacy_header_ignored_when_secret_set(monkeypatch):
    monkeypatch.setenv("OWUI_USER_JWT_SECRET", SECRET)
    uid, _ = extract_identity({b"x-jawafdehi-user-id": b"owui-cw-1"})
    assert uid is None


def test_legacy_header_used_when_secret_unset(monkeypatch):
    monkeypatch.delenv("OWUI_USER_JWT_SECRET", raising=False)
    uid, uname = extract_identity(
        {b"x-jawafdehi-user-id": b"owui-cw-1", b"x-jawafdehi-user-name": b"cw"}
    )
    assert uid == "owui-cw-1"
    assert uname == "cw"
