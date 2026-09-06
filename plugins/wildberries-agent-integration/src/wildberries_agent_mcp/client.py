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
    """Small client that forwards the caller OAuth bearer to Seller Gateway."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def verify_agent_token(self, authorization: str) -> None:
        """Verify an agent bearer without requiring a linked Seller supplier."""
        if not authorization.startswith("Bearer "):
            raise GatewayError("auth_required", status=401)
        await self.request(
            authorization=authorization,
            path="/agent/identity",
            method="GET",
            request_id=None,
        )

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

        if not path.lstrip("/").startswith("agent/"):
            path = f"/agent/{path.lstrip('/')}"
        return await self._request_http(
            authorization=authorization,
            path=path,
            method=method,
            params=params,
            json=json,
            request_id=request_id,
        )

    async def _request_http(
        self,
        *,
        authorization: str,
        path: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[int] | None = None,
        request_id: str | None = None,
    ) -> Any:
        headers = {"Authorization": authorization}
        if request_id:
            headers["X-Request-ID"] = request_id

        url = f"{self.settings.gateway_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout_seconds
            ) as client:
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
            error_code = _status_code(response.status_code)
            try:
                detail = response.json().get("detail")
            except (AttributeError, ValueError):
                detail = None
            if detail in {
                "seller_link_required",
                "seller_account_unavailable",
                "agent_route_not_allowed",
            }:
                error_code = detail
            raise GatewayError(error_code, status=response.status_code)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as error:
            raise GatewayError("upstream_invalid_json") from error


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
