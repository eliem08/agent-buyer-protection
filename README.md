<!-- sell-kit:start -->
# Agent Buyer Protection

[![CI](https://github.com/eliem08/agent-buyer-protection/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/agent-buyer-protection/actions/workflows/ci.yml)

> **Stop your agent buying the wrong thing, and get your money back when it does.**

**Who it's for:** Agentic-commerce apps and the consumers who let agents shop for them.

**The problem:** Shopping agents buy the wrong size, the wrong quantity or from the wrong store, and nobody is responsible for fixing it.

**What you get:** Check every order against the buyer's mandate before checkout, then route claims to cancel, return, chargeback or protection fund with exact refund math, and pay refunds through Stripe on the original payment.

## Quickstart

Customers receive a release archive with the wheel and the examples. Python 3.10+ and no other dependencies.

```bash
pip install agent_buyer_protection-0.1.0-py3-none-any.whl
agent-buyer-protection mandate-add shoes --description "trail running shoes" --keywords trail shoe --attr size=10 --max-total 130 --store protection.json
agent-buyer-protection order-check shoes --order-id o1 --merchant RunCo --title "Road Sandal" --unit-price 900 --attr size=10 --store protection.json
agent-buyer-protection claim-open o1 --shipped --not-returnable --not-card --store protection.json
```

## Web app and API

Every command is also a JSON API endpoint and a browser form, served by the built-in web app.

```bash
agent-buyer-protection-web --port 8000          # then open http://127.0.0.1:8000
agent-buyer-protection-web keys create --label "first customer"   # prints an API key (stored hashed)
docker build -t agent-buyer-protection . && docker run -p 8000:8000 -e API_KEYS=sk_... -v agent-buyer-protection-data:/data agent-buyer-protection
```

Every API call needs `Authorization: Bearer <key>` once any key exists; a server on a public address refuses to start without one. Calls are rate-limited per key (60/min, `--rate`) and metered: `agent-buyer-protection-web usage` prints calls per key for billing.

Endpoints: `POST /api/demo`, `POST /api/check`, `POST /api/mandate-add`, `POST /api/order-check`, `POST /api/claim-open`, `POST /api/claim-advance`, `POST /api/refund`, `POST /api/cases`, `POST /api/mandates`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Deploy and sell

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/eliem08/agent-buyer-protection)

`render.yaml` (one click, above) and `fly.toml` (`fly launch --copy-config`) both run the Dockerfile with a persistent `/data` volume and a `/healthz` check.
To sell self-serve, set four variables and point a Stripe webhook at `https://<your-host>/billing/webhook` (events `checkout.session.completed` and `customer.subscription.deleted`):

| Variable | Example |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` |
| `STRIPE_PRICES` | `team=price_123,business=price_456` |
| `PUBLIC_URL` | `https://agent-buyer-protection.example.com` |
| `PLAN_QUOTAS` (optional) | `team=10000,business=250000` successful calls per key per month |

Buyers pick a plan on `/pricing`, pay on Stripe Checkout and see their API key once on the success page. Cancelling the subscription revokes the key. A selling server always requires a key.

## Pricing

Monthly plans start with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Developer** | $49 per month | 10,000 order checks a month; Mandate violations with severity; Claims desk |
| **Growth** | $399 per month | 250,000 checks a month; Stored purchase mandates; Case and refund reports |
| **Protection** | Custom (per-order fee, contact sales) | Claims handling; SLA |

To start a trial or buy a plan, [request access](https://github.com/eliem08/agent-buyer-protection/issues/new?title=Agent%20Buyer%20Protection%20trial&labels=sales).

Plan note: every plan runs the same software, and every API key unlocks all of it. Monthly call volumes are
enforced when `PLAN_QUOTAS` is set (see Deploy and sell); seat and agent limits are licence terms the code does
not enforce. Support, SLA and done-for-you items are services.

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
- **Refunds paid through Stripe** by the business that took the payment:
  - `refund CASE --payment-intent pi_...` refunds the case amount on the original payment and moves the case to
    resolved, or to paid if it had been escalated.
  - The Stripe idempotency key comes from the case and amount, so a retry after a timeout cannot refund twice. A
    case that is already resolved or paid is refused before any call to Stripe.
  - Set `REFUNDS_STRIPE_KEY` to that account's secret key. It is kept separate from `STRIPE_SECRET_KEY`, which
    the hosted server uses to sell its own plans.
  - Chargebacks and protection-fund payouts to the shopper are still handled outside the software.
  - Tested against a stand-in for Stripe's Refunds API, not yet against a live account.

## Quickstart

```bash
pip install -e .
agent-buyer-protection demo
REFUNDS_STRIPE_KEY=sk_live_... agent-buyer-protection refund CASE-0001 --payment-intent pi_3Ab...
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
