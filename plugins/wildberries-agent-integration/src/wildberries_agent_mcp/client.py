from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import Settings


@dataclass(frozen=True, slots=True)
class GatewayError(Exception):
    code: str
    status: int | None = None

    def __str__(self) -> str:
        return self.code


class SellerGatewayClient:
    """Small, credential-preserving client for the authenticated Seller gateway."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def verify_agent_token(self, authorization: str) -> None:
        """Reject an invalid public MCP bearer before exposing authenticated tools."""
        if not authorization.startswith("Bearer "):
            raise GatewayError("auth_required", status=401)
        if self.settings.requires_identity_bridge:
            await self._resolve_authorization(authorization, request_id=None)

    async def request(
        self,
        *,
        authorization: str,
        path: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[int] | None = None,
        request_id: str | None = None,
    ) -> Any:
        if not self.settings.gateway_url:
            raise GatewayError("gateway_not_configured")
        if not authorization.startswith("Bearer "):
            raise GatewayError("auth_required", status=401)
        if not _safe_service_url(
            self.settings.gateway_url,
            require_https=self.settings.requires_identity_bridge,
        ):
            raise GatewayError(
                "gateway_https_required"
                if self.settings.requires_identity_bridge
                else "gateway_url_invalid"
            )

        gateway_authorization = await self._resolve_authorization(
            authorization, request_id
        )

        headers = {"Authorization": gateway_authorization}
        if request_id:
            headers["X-Request-ID"] = request_id

        url = f"{self.settings.gateway_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=headers,
                )
        except httpx.TimeoutException as error:
            raise GatewayError("upstream_timeout") from error
        except httpx.RequestError as error:
            raise GatewayError("upstream_unavailable") from error

        if response.status_code >= 400:
            raise GatewayError(
                _status_code(response.status_code), status=response.status_code
            )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as error:
            raise GatewayError("upstream_invalid_json") from error

    async def _resolve_authorization(
        self, authorization: str, request_id: str | None
    ) -> str:
        if not self.settings.requires_identity_bridge:
            return authorization
        if not self.settings.identity_bridge_url:
            raise GatewayError("identity_bridge_not_configured")
        if not _safe_service_url(self.settings.identity_bridge_url, require_https=True):
            raise GatewayError("identity_bridge_https_required")

        headers = {
            "Authorization": authorization,
            "X-Identity-Audience": "seller-gateway",
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.post(
                    self.settings.identity_bridge_url,
                    headers=headers,
                )
        except httpx.TimeoutException as error:
            raise GatewayError("identity_bridge_timeout") from error
        except httpx.RequestError as error:
            raise GatewayError("identity_bridge_unavailable") from error

        if response.status_code >= 400:
            raise GatewayError("identity_bridge_rejected", status=response.status_code)
        try:
            payload = response.json()
        except ValueError as error:
            raise GatewayError("identity_bridge_invalid_json") from error
        token = payload.get("seller_access_token") or payload.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise GatewayError("identity_bridge_missing_token")
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token or any(character.isspace() for character in token):
            raise GatewayError("identity_bridge_invalid_token")
        return f"Bearer {token}"


def _status_code(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        408: "timeout",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
    }.get(status, "upstream_error")


def _safe_service_url(url: str, *, require_https: bool) -> bool:
    try:
        parts = urlsplit(url)
        username = parts.username
        password = parts.password
    except ValueError:
        return False
    schemes = {"https"} if require_https else {"http", "https"}
    return (
        parts.scheme in schemes
        and bool(parts.netloc)
        and not username
        and not password
        and not parts.query
        and not parts.fragment
    )
