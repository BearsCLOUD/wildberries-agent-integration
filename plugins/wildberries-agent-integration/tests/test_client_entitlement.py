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
