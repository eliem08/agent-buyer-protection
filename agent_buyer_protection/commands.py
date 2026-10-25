"""Stateless commands: read a JSON request, print a JSON decision (also served by the web app)."""

import json
from datetime import date

from .core import ClaimDesk, Mandate, Order, check, decide


def _d(v):
    return date.fromisoformat(v) if v else None


def add_commands(sub):
    c = sub.add_parser("check", help="check an order against the buyer's mandate before checkout")
    c.add_argument("request", help="JSON with a mandate and an order")


def run(a):
    with open(a.request, encoding="utf-8-sig") as fh:
        req = json.load(fh)
    if not isinstance(req, dict) or not isinstance(req.get("mandate"), dict) or not isinstance(req.get("order"), dict):
        raise ValueError("request must be an object with 'mandate' and 'order' objects")
    md, od = dict(req["mandate"]), dict(req["order"])
    md["deliver_by"], od["eta"] = _d(md.get("deliver_by")), _d(od.get("eta"))
    m, o = Mandate(**md), Order(**od)
    violations = check(m, o)
    decision = decide(violations)
    if not o.shipped:
        path = "cancel"
    elif o.returnable:
        path = "merchant_return"
    elif o.paid_by_card:
        path = "chargeback"
    else:
        path = "protection_fund"
    out = {
        "decision": decision,
        "violations": [v.__dict__ for v in violations],
        "refund_if_claimed": ClaimDesk.refund_amount(m, o, violations) if violations else 0.0,
        "claim_path": path if violations else None,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0 if decision == "allow" else 1
