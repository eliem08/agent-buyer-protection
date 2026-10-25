<!-- sell-kit:start -->
# Agent Buyer Protection

[![CI](https://github.com/eliem08/agent-buyer-protection/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/agent-buyer-protection/actions/workflows/ci.yml)

> **Stop your agent buying the wrong thing, and get your money back when it does.**

**Who it's for:** Agentic-commerce apps and the consumers who let agents shop for them.

**The problem:** Shopping agents buy the wrong size, the wrong quantity or from the wrong store, and nobody is responsible for fixing it.

**What you get:** Check every order against the buyer's mandate before checkout, then route claims to cancel, return, chargeback or protection fund with exact refund math.

## Quickstart

Customers receive a release archive with the wheel and the examples. Python 3.10+ and no other dependencies.

```bash
pip install agent_buyer_protection-0.1.0-py3-none-any.whl
agent-buyer-protection check examples/order-check.json
agent-buyer-protection demo
```

## Web app and API

Every command is also a JSON API endpoint and a browser form, served by the built-in web app.

```bash
agent-buyer-protection-web --port 8000          # then open http://127.0.0.1:8000
agent-buyer-protection-web keys create --label "first customer"   # prints an API key (stored hashed)
docker build -t agent-buyer-protection . && docker run -p 8000:8000 -e API_KEYS=sk_... -v agent-buyer-protection-data:/data agent-buyer-protection
```

Every API call needs `Authorization: Bearer <key>` once any key exists; a server on a public address refuses to start without one. Calls are rate-limited per key (60/min, `--rate`) and metered: `agent-buyer-protection-web usage` prints calls per key for billing.

Endpoints: `POST /api/demo`, `POST /api/check`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Pricing

Every plan starts with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Developer** | $49 per month | 10,000 order checks a month; Mandate violations with severity; Claims desk |
| **Growth** | $399 per month | 250,000 checks a month; Custom rules; Refund reporting |
| **Protection** | Custom (per-order fee, contact sales) | Backed buyer-protection program; Claims handling; SLA |

To start a trial or buy a plan, [request access](https://github.com/eliem08/agent-buyer-protection/issues/new?title=Agent%20Buyer%20Protection%20trial&labels=sales).

## Licence

Proprietary. Copyright (c) 2026 eliem08. All rights reserved. Use requires a paid plan or an active trial; see [LICENSE](LICENSE).
<!-- sell-kit:end -->

## What it does

- **Mandates**: what the human actually authorised — keywords, required
  attributes (size, colour…), max unit price, max total, quantity, merchant
  allow/deny lists, deliver-by date
- **Pre-checkout check**: `check(mandate, order)` → list of violations with severity;
  `block` / `confirm_with_human` / `allow`
- **Claims engine** for completed orders:
  - picks the cheapest resolution path: *cancel* (not shipped) → *merchant return*
    → *card chargeback* → *protection fund payout*
  - refund amount including overspend-only refunds (wrong price, right item)
  - case state machine: `opened → merchant_contacted → resolved / escalated → paid`
- Evidence bundle (mandate vs. order diff) attached to every claim

## Quickstart

```bash
pip install -e .
agent-buyer-protection demo
```

## Roadmap

- Signed mandates (AP2 / verifiable intent) checked at merchant checkout
- Merchant network with instant-cancel APIs
- Protection-fund underwriting (pairs with agent-insure and agentrust)

## Development

Zero runtime dependencies; Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m unittest discover -s tests -t .           # unit + CLI smoke tests
ruff check . && ruff format --check .               # lint + format
```

```
agent_buyer_protection/core.py       domain logic (pure, importable, fully tested)
agent_buyer_protection/__main__.py   CLI (`agent-buyer-protection ...` / `python -m agent_buyer_protection ...`)
tests/                unit tests + generated CLI smoke tests
```

CI runs lint and tests on Ubuntu and Windows across Python 3.10, 3.12 and 3.13.
Design, data model, trade-offs and production path: **[ARCHITECTURE.md](ARCHITECTURE.md)**.

Part of the [agent-economy](https://github.com/eliem08/agent-economy) portfolio (idea #15).
