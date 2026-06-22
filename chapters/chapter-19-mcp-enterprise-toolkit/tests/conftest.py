"""共享 pytest fixture。

- 把仓库根目录加入 ``sys.path``，让 ``from mcp_gateway import ...`` 在
  tests 目录下直接可用；
- 提供 ``gateway`` / ``oauth_config`` / ``signed_token`` fixture。
"""
from __future__ import annotations

import os
import sys
import time

import pytest

# 把 chapter-19 根目录加到 sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


HS256_SECRET = "test-secret-only-for-pytest"


@pytest.fixture
def gateway():
    """开箱即用的 Gateway（每个用例独立实例，避免限流桶共享）。"""
    from mcp_gateway import build_default_gateway

    return build_default_gateway(secret=HS256_SECRET)


@pytest.fixture
def oauth_config():
    """与 gateway 内部 OAuthConfig 一致的副本，用于直接调 verify_access_token."""
    from oauth_middleware import OAuthConfig

    return OAuthConfig(
        issuer="https://auth.acme.example",
        resource="https://mcp.acme.example",
        hs256_secret=HS256_SECRET,
        audience="enterprise-mcp-gateway",
    )


@pytest.fixture
def make_token(oauth_config):
    """生成一个有效 / 可定制的 Bearer Token。"""
    from oauth_middleware import issue_hs256_token

    def _make(
        *,
        sub: str = "alice",
        tenant: str = "acme",
        scope: str = "mcp.read mcp.tools",
        resource: str | None = None,
        audience: str | None = None,
        exp_in: int = 3600,
        nbf: int | None = None,
        issuer: str | None = None,
    ) -> str:
        now = int(time.time())
        payload = {
            "iss": issuer or oauth_config.issuer,
            "aud": audience if audience is not None else oauth_config.audience,
            "sub": sub,
            "tenant": tenant,
            "scope": scope,
            "resource": resource or oauth_config.resource,
            "iat": now,
            "exp": now + exp_in,
            "nbf": nbf or now,
        }
        return "Bearer " + issue_hs256_token(payload, oauth_config.hs256_secret)

    return _make


@pytest.fixture(autouse=True)
def _reset_tracer():
    """每个用例前后清空全局 tracer，避免相互污染。"""
    from observability import get_tracer

    get_tracer().reset()
    yield
    get_tracer().reset()
