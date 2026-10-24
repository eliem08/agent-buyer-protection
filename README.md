# agent-buyer-protection

> **PayPal Buyer Protection for agent purchases** — fixes it when your agent buys the wrong thing.

You asked your agent for "size 10 black running shoes under $120". It bought
three pairs of size 1 brown loafers for $340 from a sketchy store. Who catches
that, and who unwinds it? `agent-buyer-protection` compares every agent
purchase against the human's **mandate**, flags mismatches before money
moves, and runs the claim when something slips through.

## What the MVP does

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
- Protection-fund underwriting (pairs with agent-insure and agent-fico)
