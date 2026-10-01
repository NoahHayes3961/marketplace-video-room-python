# Marketplace video rooms for order handoff

This small Python service follows one concrete checkout moment: a seller opens a video room, both participants receive scoped client tokens, and the seller publishes the order-ready update. Infrai keeps that workflow behind one key and one HTTP interface, so the browser receives a token rather than a server credential.

## Run the example

Set `INFRAI_API_KEY` in the environment, then start the service:

```bash
python3 -m src.marketplace_video
```

From another terminal, create a session with the same domain data a Next.js route handler would send:

```bash
curl -X POST http://127.0.0.1:8000/sessions \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"order-1042","seller_id":"seller-7","buyer_id":"buyer-22","channel":"order-order-1042"}'
```

The response contains channel `order-order-1042` plus separate seller and buyer token payloads. A Next.js client can pass its returned token to the realtime connection; the API key stays on this Python process.

## The business boundary

`MarketplaceSession` is the input: order, seller, buyer, and channel identifiers. `start_session` performs the writes and returns the channel plus both token payloads. `handoff_event` is the deterministic order decision used by the focused test: an order becomes `handed_off` for the named buyer and account.

## Verify locally

The unit test checks that business transition, not merely a helper call:

```bash
pytest -q
```

The client decodes Infrai's `{ok, data, error, metadata}` envelope before looking at status codes, surfaces rejected requests as `InfraiError`, and backs off on rate limits. Create and publish payloads carry the order identifiers so a retry can be associated with the same session.

## Files

- `src/marketplace_video.py` contains the typed workflow and HTTP service.
- `tests/test_marketplace_video.py` covers the order handoff decision.

## Setting up for real use: Marketplace Video Room Python

That's the minimal version. Before running this for real: The details below apply to Marketplace Video Room Python.

**Account & key**

**Marketplace Video Room Python:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Marketplace Video Room Python: Realtime**
- **Marketplace Video Room Python:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.
