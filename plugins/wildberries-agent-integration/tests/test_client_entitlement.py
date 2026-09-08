import asyncio
from typing import ClassVar

import httpx
import pytest

from wildberries_agent_mcp.client import GatewayError, SellerGatewayClient
from wildberries_agent_mcp.config import Settings


class FakeAsyncClient:
    requests: ClassVar[list[dict]] = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def request(self, **kwargs):
        self.requests.append({"kind": "request", **kwargs})
        return httpx.Response(200, json={"ok": True})


def test_production_gateway_call_forwards_opaque_agent_bearer_directly(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = SellerGatewayClient(
        Settings(
            environment="production",
            gateway_url="https://gateway.example.test",
        )
    )

    result = asyncio.run(
        client.request(
            authorization="Bearer opaque-agent-token",
            path="/agent/financial_report/dashboard/v2",
        )
    )

    assert result == {"ok": True}
    gateway_call = FakeAsyncClient.requests[-1]
    assert gateway_call["headers"] == {"Authorization": "Bearer opaque-agent-token"}


@pytest.mark.parametrize(
    "code",
    [
        "confirmation_required",
        "confirmation_expired",
        "confirmation_mismatch",
        "write_status_unknown",
    ],
)
def test_cost_confirmation_errors_preserve_only_owned_codes(monkeypatch, code) -> None:
    class ErrorClient(FakeAsyncClient):
        async def request(self, **kwargs):
            return httpx.Response(
                409,
                json={
                    "ok": False,
                    "error": {"code": code, "message": "provider text is ignored"},
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", ErrorClient)
    client = SellerGatewayClient(
        Settings(environment="production", gateway_url="https://gateway.example.test")
    )

    with pytest.raises(GatewayError) as raised:
        asyncio.run(
            client.request(
                authorization="Bearer opaque-agent-token",
                path="/agent/price_management/cost_price",
                method="PUT",
                json={"nm_id": 1, "cost_price": 2.0, "confirm": True},
            )
        )

    assert raised.value.code == code
    assert raised.value.status == 409


@pytest.mark.parametrize(
    ("path", "payload", "expected"),
    [
        (
            "/agent/other",
            {"error": {"code": "confirmation_expired"}},
            "conflict",
        ),
        (
            "/agent/price_management/cost_price",
            {"error": {"code": ["confirmation_expired"]}},
            "conflict",
        ),
        (
            "/agent/price_management/cost_price",
            {"detail": [{"loc": ["body"], "msg": "invalid"}]},
            "conflict",
        ),
    ],
)
def test_gateway_error_parser_fails_closed_for_unowned_or_malformed_codes(
    monkeypatch, path, payload, expected
) -> None:
    class ErrorClient(FakeAsyncClient):
        async def request(self, **kwargs):
            return httpx.Response(409, json=payload)

    monkeypatch.setattr(httpx, "AsyncClient", ErrorClient)
    client = SellerGatewayClient(
        Settings(environment="production", gateway_url="https://gateway.example.test")
    )

    with pytest.raises(GatewayError) as raised:
        asyncio.run(
            client.request(
                authorization="Bearer opaque-agent-token",
                path=path,
            )
        )

    assert raised.value.code == expected
