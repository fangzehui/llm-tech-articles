"""OAuth 2.1 中间件：PKCE + Resource Indicator + JWT 校验。

MCP 2025-06-18 / 2025-11-25 规范关键变化
----------------------------------------
- MCP Server 是一个标准 **OAuth Resource Server**，对外提供
  ``.well-known/oauth-protected-resource`` 元数据；
- 远端 Client 必须使用 **OAuth 2.1**（PKCE 强制、隐式流被禁用）；
- 调用 Resource Server 的 access_token 必须带 ``aud`` claim 或在请求中
  携带 **Resource Indicator (RFC 8707)**，防止跨 Server 的 token 透传。

本模块只做"校验"，不做"发token"。
真正的 Authorization Server 应该是企业自有的 OIDC IdP（Okta / Azure AD /
Keycloak / Logto 等），本模块只承担 RS 端的验证职责。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any


# --------------------- 异常 ---------------------


class OAuthError(Exception):
    """OAuth 校验失败统一基类。子类映射到不同 HTTP 状态码。"""

    status_code = 401
    error_code = "invalid_token"


class TokenExpired(OAuthError):
    error_code = "invalid_token"


class InvalidSignature(OAuthError):
    error_code = "invalid_token"


class InvalidAudience(OAuthError):
    """``aud`` 不匹配，可能是别的 RS 的 token 被透传过来了。"""

    error_code = "invalid_token"


class InvalidResource(OAuthError):
    """``resource`` 参数 / claim 不匹配（RFC 8707 Resource Indicator）。"""

    error_code = "invalid_target"


class InsufficientScope(OAuthError):
    status_code = 403
    error_code = "insufficient_scope"


class PKCEError(OAuthError):
    status_code = 400
    error_code = "invalid_grant"


# --------------------- JWT 极简实现 ---------------------
# 业务上推荐 PyJWT，本文件用最小实现，方便单测且不依赖外网 / IdP。


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_hs256_token(
    payload: dict[str, Any], secret: str, header_extra: dict[str, Any] | None = None
) -> str:
    """签发 HS256 JWT，仅供单元测试与本地 demo。

    生产请用 RS256/ES256 + JWKS，且签发由 IdP 完成，**不要把 secret 放进 RS**。
    """
    header = {"alg": "HS256", "typ": "JWT"}
    if header_extra:
        header.update(header_extra)
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def _verify_hs256(token: str, secret: str) -> dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
    except ValueError as e:
        raise InvalidSignature(f"JWT 结构错误：{e}") from e

    expected = hmac.new(secret.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(s_b64)):
        raise InvalidSignature("HS256 签名不匹配")
    payload: dict[str, Any] = json.loads(_b64url_decode(p_b64))
    return payload


# --------------------- 配置 ---------------------


@dataclass
class OAuthConfig:
    """RS 侧 OAuth 验证配置。

    生产配置应来自 K8s ConfigMap / Secret，本类只是接口约定。
    """

    issuer: str  # 期望的 ``iss``，如 "https://auth.acme.com"
    resource: str  # 本 RS 的资源标识，如 "https://mcp.acme.com"
    hs256_secret: str  # 单测用，生产应使用 JWKS
    audience: str | None = None  # 若设置，校验 ``aud`` claim
    leeway_seconds: int = 30


# --------------------- 主验证逻辑 ---------------------


def verify_access_token(
    bearer_token: str,
    config: OAuthConfig,
    *,
    required_scope: str | None = None,
    expected_resource: str | None = None,
) -> dict[str, Any]:
    """校验 Bearer Access Token，返回 payload。

    - 校验签名（HS256）
    - 校验 ``iss``、``exp``、``nbf``、``aud``
    - 校验 ``resource`` claim（RFC 8707）防 token 透传
    - 校验 ``scope`` 至少包含 required_scope

    任何失败抛出 ``OAuthError`` 子类。
    """
    if not bearer_token or not bearer_token.startswith("Bearer "):
        raise OAuthError(
            "缺少 Bearer Access Token；MCP Gateway 拒绝匿名调用"
        )
    raw = bearer_token[len("Bearer "):].strip()

    payload = _verify_hs256(raw, config.hs256_secret)

    now = int(time.time())
    # iss
    if payload.get("iss") != config.issuer:
        raise InvalidSignature(
            f"iss 不匹配：期望 {config.issuer!r}，实际 {payload.get('iss')!r}"
        )
    # exp / nbf
    exp = payload.get("exp")
    if exp is None or now > exp + config.leeway_seconds:
        raise TokenExpired(f"token 已过期；exp={exp}, now={now}")
    nbf = payload.get("nbf", 0)
    if now + config.leeway_seconds < nbf:
        raise TokenExpired(f"token 尚未生效；nbf={nbf}, now={now}")
    # aud
    if config.audience:
        aud = payload.get("aud")
        ok = aud == config.audience or (
            isinstance(aud, list) and config.audience in aud
        )
        if not ok:
            raise InvalidAudience(
                f"aud 不匹配：期望 {config.audience!r}，实际 {aud!r}"
            )
    # resource (RFC 8707 Resource Indicator)
    expected_res = expected_resource or config.resource
    res_claim = payload.get("resource")
    if isinstance(res_claim, list):
        ok = expected_res in res_claim
    else:
        ok = res_claim == expected_res
    if not ok:
        raise InvalidResource(
            "resource 不匹配；token 可能是其它 RS 的 token 被透传过来 "
            f"(expected={expected_res}, got={res_claim})"
        )
    # scope
    if required_scope:
        scope_str = payload.get("scope") or payload.get("scp") or ""
        scopes = scope_str.split() if isinstance(scope_str, str) else list(scope_str)
        if required_scope not in scopes:
            raise InsufficientScope(
                f"缺少 scope：{required_scope}（当前 {scopes}）"
            )
    return payload


# --------------------- PKCE ---------------------


def generate_pkce_pair() -> tuple[str, str]:
    """生成 PKCE 的 ``(verifier, challenge_S256)``。

    符合 RFC 7636：verifier 长度 43-128，charset 是 ``[A-Z][a-z][0-9]-._~``，
    challenge = BASE64URL(SHA256(verifier))。
    """
    verifier = _b64url_encode(os.urandom(48))[:64]
    challenge = _b64url_encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def verify_pkce(verifier: str, challenge: str, method: str = "S256") -> None:
    """authorization_code 兑换时由 Authorization Server 调用。

    MCP 2025-06-18 之后 ``plain`` 已被废弃，本函数只接受 ``S256``。
    """
    if method.upper() != "S256":
        raise PKCEError(f"MCP 强制使用 S256，禁止 method={method}")
    if not (43 <= len(verifier) <= 128):
        raise PKCEError(f"PKCE verifier 长度非法：{len(verifier)}")
    expected = _b64url_encode(hashlib.sha256(verifier.encode()).digest())
    if not hmac.compare_digest(expected, challenge):
        raise PKCEError("PKCE 校验失败：verifier 与 challenge 不匹配")


# --------------------- .well-known 元数据构造 ---------------------


def build_protected_resource_metadata(
    resource: str,
    authorization_servers: list[str],
    scopes_supported: list[str] | None = None,
) -> dict[str, Any]:
    """构造 ``/.well-known/oauth-protected-resource`` 响应体。

    MCP 2025-11-25 规范规定 RS 必须在这个 endpoint 公布其 AS 位置。
    """
    return {
        "resource": resource,
        "authorization_servers": authorization_servers,
        "scopes_supported": scopes_supported or ["mcp.read", "mcp.tools"],
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": ["RS256", "ES256"],
    }


__all__ = [
    "OAuthConfig",
    "OAuthError",
    "TokenExpired",
    "InvalidSignature",
    "InvalidAudience",
    "InvalidResource",
    "InsufficientScope",
    "PKCEError",
    "issue_hs256_token",
    "verify_access_token",
    "generate_pkce_pair",
    "verify_pkce",
    "build_protected_resource_metadata",
]
