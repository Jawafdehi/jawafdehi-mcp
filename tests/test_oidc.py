"""Tests for OIDC bearer-token verification and identity resolution."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from jawafdehi_mcp import oidc

ISSUER = "https://auth.test.invalid"
AUDIENCE = "test-project-id"


@pytest.fixture(autouse=True)
def _oidc_env(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_API_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://auth.test.invalid/keys")
    monkeypatch.setenv("OIDC_OP_USER_ENDPOINT", "https://auth.test.invalid/userinfo")
    # Reset module caches between tests.
    oidc._jwks_client = None
    oidc._userinfo_cache.clear()


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _fake_jwks(monkeypatch, rsa_key):
    """Make verify use our test key instead of fetching a real JWKS."""

    class _SigningKey:
        key = rsa_key.public_key()

    class _FakeClient:
        def get_signing_key_from_jwt(self, token):
            return _SigningKey()

    monkeypatch.setattr(oidc, "_get_jwks_client", lambda: _FakeClient())


def _mint(rsa_key, **overrides):
    now = int(time.time())
    payload = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": now + 300,
        "iat": now,
        "jti": "jti-1",
    }
    payload.update(overrides)
    return jwt.encode(payload, rsa_key, algorithm="RS256")


class TestVerifyBearerToken:
    def test_valid_token(self, rsa_key):
        claims = oidc.verify_bearer_token(_mint(rsa_key))
        assert claims["sub"] == "user-123"

    def test_jwe_rejected(self):
        with pytest.raises(oidc.OIDCError):
            oidc.verify_bearer_token("a.b.c.d.e")

    def test_wrong_audience(self, rsa_key):
        with pytest.raises(oidc.OIDCError):
            oidc.verify_bearer_token(_mint(rsa_key, aud="other"))

    def test_wrong_issuer(self, rsa_key):
        with pytest.raises(oidc.OIDCError):
            oidc.verify_bearer_token(_mint(rsa_key, iss="https://evil.invalid"))

    def test_expired(self, rsa_key):
        with pytest.raises(oidc.OIDCError):
            oidc.verify_bearer_token(_mint(rsa_key, exp=int(time.time()) - 10))

    def test_missing_issuer_config(self, rsa_key, monkeypatch):
        monkeypatch.delenv("OIDC_ISSUER", raising=False)
        with pytest.raises(oidc.OIDCError):
            oidc.verify_bearer_token(_mint(rsa_key))


class TestBuildIdentity:
    def test_builds_from_userinfo(self):
        claims = {"sub": "abc"}
        info = {
            "email": "Jane@Example.ORG",
            "name": "Jane Doe",
            "roles": ["contributor", "staff"],
        }
        identity = oidc.build_identity(claims, info)
        assert identity == {
            "sub": "abc",
            "email": "jane@example.org",
            "name": "Jane Doe",
            "roles": ["contributor", "staff"],
        }

    def test_name_falls_back_to_given_family(self):
        identity = oidc.build_identity(
            {"sub": "x"},
            {"given_name": "Ram", "family_name": "Sharma", "email": "r@x.org"},
        )
        assert identity["name"] == "Ram Sharma"

    def test_non_list_roles_become_empty(self):
        identity = oidc.build_identity({"sub": "x"}, {"roles": "contributor"})
        assert identity["roles"] == []


@pytest.mark.asyncio
class TestFetchUserinfo:
    async def test_caches_per_token(self, monkeypatch):
        calls = {"n": 0}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"email": "a@x.org", "roles": ["admin"]}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                calls["n"] += 1
                return _Resp()

        monkeypatch.setattr(oidc.httpx, "AsyncClient", lambda *a, **k: _Client())

        claims = {"jti": "t1", "exp": time.time() + 300}
        first = await oidc.fetch_userinfo("tok", claims)
        second = await oidc.fetch_userinfo("tok", claims)
        assert first == second
        assert calls["n"] == 1
