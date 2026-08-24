import asyncio

import httpx

from wildberries_agent_mcp.client import SellerGatewayClient
from wildberries_agent_mcp.config import Settings


class FakeAsyncClient:
    requests: list[dict] = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers):
        self.requests.append({"kind": "post", "url": url, "headers": headers})
        return httpx.Response(200, json={"access_token": "seller-session"})

    async def request(self, **kwargs):
        self.requests.append({"kind": "request", **kwargs})
        return httpx.Response(200, json={"ok": True})


def test_production_gateway_call_propagates_opaque_agent_bearer_for_validation(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = SellerGatewayClient(
        Settings(
            environment="production",
            gateway_url="https://gateway.example.test",
            identity_bridge_url="https://passport.example.test/mcp/identity/exchange",
        )
    )

    result = asyncio.run(
        client.request(
            authorization="Bearer opaque-agent-token",
            path="/financial_report/dashboard/v2",
        )
    )

    assert result == {"ok": True}
    gateway_call = FakeAsyncClient.requests[-1]
    assert gateway_call["headers"] == {
        "Authorization": "Bearer seller-session",
        "X-Agent-Authorization": "Bearer opaque-agent-token",
    }
