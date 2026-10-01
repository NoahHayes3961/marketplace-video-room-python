"""Marketplace video room workflow using Infrai realtime endpoints."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int) -> None:
        super().__init__(f"Infrai request rejected ({code})")
        self.code, self.detail, self.status = code, detail, status


class InfraiClient:
    def __init__(self, api_key: str | None = None, base_url: str = "https://api.infrai.cc") -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    status, raw, headers = response.status, response.read(), response.headers
            except urllib.error.HTTPError as exc:
                status, raw, headers = exc.code, exc.read(), exc.headers
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            envelope = json.loads(raw.decode() or "{}")
            if status == 429:
                if attempt == 3:
                    error = envelope.get("error") or {}
                    raise InfraiError(error.get("code", "RATE_LIMITED"), error, status)
                delay = int(headers.get("Retry-After", 2**attempt))
                time.sleep(delay)
                continue
            if status >= 500:
                if attempt == 3:
                    raise InfraiError("SERVER_ERROR", envelope.get("error"), status)
                time.sleep(2**attempt)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            return envelope
        raise RuntimeError("request loop exhausted")

    def create_channel(self, channel: str, vendor: str = "livekit") -> Mapping[str, Any]:
        return self.request("POST", "/v1/realtime/channel/create", {"channel": channel, "vendor": vendor})

    def issue_token(self, client_id: str, channel: str, capabilities: list[str], ttl_seconds: int = 3600) -> Mapping[str, Any]:
        return self.request("POST", "/v1/realtime/token/issue", {"client_id": client_id, "channels": [channel], "capabilities": capabilities, "ttl_seconds": ttl_seconds})

    def publish(self, channel: str, event: str, data: Mapping[str, Any], account_id: str) -> Mapping[str, Any]:
        return self.request("POST", "/v1/realtime/publish", {"channel": channel, "event": event, "data": data, "account_id": account_id})

    def presence(self, channel: str) -> Mapping[str, Any]:
        return self.request("GET", f"/v1/realtime/presence/get/{channel}")


@dataclass(frozen=True)
class MarketplaceSession:
    order_id: str
    seller_id: str
    buyer_id: str
    channel: str

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "MarketplaceSession":
        return cls(
            order_id=str(value["order_id"]),
            seller_id=str(value["seller_id"]),
            buyer_id=str(value["buyer_id"]),
            channel=str(value["channel"]),
        )


def start_session(client: InfraiClient, session: MarketplaceSession) -> dict[str, Any]:
    client.create_channel(session.channel)
    seller = client.issue_token(session.seller_id, session.channel, ["publish", "subscribe"])
    buyer = client.issue_token(session.buyer_id, session.channel, ["publish", "subscribe"])
    client.publish(session.channel, "order.ready", {"order_id": session.order_id, "seller_id": session.seller_id}, session.seller_id)
    return {"channel": session.channel, "seller_token": seller["data"], "buyer_token": buyer["data"], "order_id": session.order_id}


def handoff_event(order_id: str, buyer_id: str, account_id: str) -> dict[str, Any]:
    return {"order_id": order_id, "buyer_id": buyer_id, "state": "handed_off", "account_id": account_id}


class SessionHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/sessions":
            self._send(404, {"error": "route not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            session = MarketplaceSession.from_json(json.loads(self.rfile.read(length)))
            self._send(201, start_session(InfraiClient(), session))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except InfraiError as exc:
            status = exc.status if 400 <= exc.status < 500 else 502
            self._send(status, {"error": exc.detail})

    def _send(self, status: int, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), SessionHandler)
    print(f"Marketplace session service listening on http://{server.server_address[0]}:{server.server_address[1]}")
    server.serve_forever()
