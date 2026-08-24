from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    async def request(
        self,
        *,
        authorization: str,
        path: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> Any:
        if not self.settings.gateway_url:
            raise GatewayError("gateway_not_configured")
        if not authorization.startswith("Bearer "):
            raise GatewayError("auth_required", status=401)

        headers = {"Authorization": authorization}
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
