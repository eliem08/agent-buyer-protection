"""Operating commands: mandates, pre-purchase checks and the claims desk on a persistent store.

Refunds are a ledger: the desk decides the recovery path and the amount, and `cases` shows what is owed.
Sending the money back is done through the merchant, the card network or your protection fund.
"""

import itertools
import json
import os
from dataclasses import asdict
from datetime import date

from .core import FLOW, Case, ClaimDesk, Mandate, Order, Violation, check, decide
from .refunds import REASONS, stripe_refund

OPS = ("mandate-add", "order-check", "claim-open", "claim-advance", "refund", "cases", "mandates")
EVENTS = sorted({e for nxt in FLOW.values() for e in nxt})


class DeskError(ValueError):
    pass


def _day(text):
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise DeskError(f"{text!r} is not a date like 2026-12-01") from None


def _iso(d):
    return d.isoformat() if d else None


def pairs(items) -> dict:
    out = {}
    for item in items or []:
        k, sep, v = item.partition("=")
        if not sep or not k.strip():
            raise DeskError(f"--attr must look like name=value, got {item!r}")
        out[k.strip()] = v.strip()
    return out


class State:
    def __init__(self, path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8-sig") as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            doc = {}
        if not isinstance(doc, dict):
            raise DeskError(f"{path}: not an agent-buyer-protection store")
        self.mandates = {}
        for k, m in doc.get("mandates", {}).items():
            self.mandates[k] = Mandate(**{**m, "deliver_by": _day(m.get("deliver_by"))})
        self.orders = {}  # order_id -> (mandate_id, Order)
        for k, rec in doc.get("orders", {}).items():
            self.orders[k] = (rec["mandate"], Order(**{**rec["order"], "eta": _day(rec["order"].get("eta"))}))
        self.desk = ClaimDesk(float(doc.get("fund_limit", 500.0)))
        self.desk.fund_paid = float(doc.get("fund_paid", 0.0))
        self.desk._ids = itertools.count(int(doc.get("next_id", 1)))
        for k, c in doc.get("cases", {}).items():
            order = Order(**{**c["order"], "eta": _day(c["order"].get("eta"))})
            violations = [Violation(**v) for v in c["violations"]]
            history = [tuple(h) for h in c["history"]]
            self.desk.cases[k] = Case(k, order, violations, c["path"], c["refund"], c["state"], history)

    def save(self):
        next_id = next(self.desk._ids)
        self.desk._ids = itertools.count(next_id)

        def order(o: Order) -> dict:
            return {**asdict(o), "eta": _iso(o.eta)}

        doc = {
            "mandates": {k: {**asdict(m), "deliver_by": _iso(m.deliver_by)} for k, m in self.mandates.items()},
            "orders": {k: {"mandate": mid, "order": order(o)} for k, (mid, o) in self.orders.items()},
            "cases": {
                k: {
                    "order": order(c.order),
                    "violations": [asdict(v) for v in c.violations],
                    "path": c.path,
                    "refund": c.refund,
                    "state": c.state,
                    "history": c.history,
                }
                for k, c in self.desk.cases.items()
            },
            "fund_limit": self.desk.fund_limit,
            "fund_paid": self.desk.fund_paid,
            "next_id": next_id,
        }
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        os.replace(tmp, self.path)


def add_ops(sub):
    store = os.environ.get("AGENT_BUYER_PROTECTION_STORE", "protection.json")
    p = sub.add_parser("mandate-add", help="record what the user actually asked the agent to buy")
    p.add_argument("mandate_id")
    p.add_argument("--description", required=True)
    p.add_argument("--keywords", nargs="*", default=[], help="words the product title must contain")
    p.add_argument("--attr", action="append", default=[], help="required attribute, e.g. size=10 (repeatable)")
    p.add_argument("--max-unit-price", type=float)
    p.add_argument("--max-total", type=float)
    p.add_argument("--quantity", type=int, default=1)
    p.add_argument("--merchant-allow", nargs="*", default=[])
    p.add_argument("--merchant-deny", nargs="*", default=[])
    p.add_argument("--deliver-by", help="YYYY-MM-DD")
    p = sub.add_parser("order-check", help="before the agent pays: allow, ask the human, or block")
    p.add_argument("mandate_id")
    p.add_argument("--order-id", required=True)
    p.add_argument("--merchant", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--unit-price", type=float, required=True)
    p.add_argument("--quantity", type=int, default=1)
    p.add_argument("--shipping", type=float, default=0.0)
    p.add_argument("--eta", help="YYYY-MM-DD")
    p.add_argument("--attr", action="append", default=[], help="the listing's attribute, e.g. size=10")
    p = sub.add_parser("claim-open", help="a checked order went wrong: open a case and pick the recovery path")
    p.add_argument("order_id")
    p.add_argument("--shipped", action="store_true")
    p.add_argument("--not-returnable", action="store_true")
    p.add_argument("--not-card", action="store_true", help="not paid by card, so no chargeback")
    p = sub.add_parser("claim-advance", help="move a case forward")
    p.add_argument("case_id")
    p.add_argument("event", choices=EVENTS)
    p = sub.add_parser("refund", help="pay the case's refund through Stripe on the original payment")
    p.add_argument("case_id")
    p.add_argument("--payment-intent", required=True, help="the original Stripe payment: pi_... or ch_...")
    p.add_argument("--reason", choices=REASONS, default="requested_by_customer")
    sub.add_parser("cases", help="every case, its path, state and refund")
    sub.add_parser("mandates", help="every mandate on file")
    for name in OPS:
        sub.choices[name].add_argument("--store", default=store)


def run_ops(a) -> int:
    try:
        st = State(a.store)
        code = _run(st, a)
        st.save()
        return code
    except ValueError as e:
        print(f"refused: {e}")
        return 1


def _run(st: State, a) -> int:
    c = a.cmd
    if c == "mandate-add":
        if a.mandate_id in st.mandates:
            raise DeskError(f"mandate {a.mandate_id!r} already exists")
        if a.quantity < 1:
            raise DeskError("quantity must be at least 1")
        st.mandates[a.mandate_id] = Mandate(
            a.description,
            a.keywords,
            pairs(a.attr),
            a.max_unit_price,
            a.max_total,
            a.quantity,
            a.merchant_allow,
            a.merchant_deny,
            _day(a.deliver_by),
        )
        print(f"mandate {a.mandate_id}: {a.description}")
    elif c == "order-check":
        if a.mandate_id not in st.mandates:
            raise DeskError(f"no mandate {a.mandate_id!r}")
        o = Order(a.order_id, a.merchant, a.title, a.unit_price, a.quantity, pairs(a.attr), a.shipping, _day(a.eta))
        violations = check(st.mandates[a.mandate_id], o)
        verdict = decide(violations)
        st.orders[a.order_id] = (a.mandate_id, o)
        print(verdict.upper())
        for v in violations:
            print(f"  [{v.severity}] {v.rule}: {v.detail}")
        return 0 if verdict == "allow" else 1
    elif c == "claim-open":
        if a.order_id not in st.orders:
            raise DeskError(f"no checked order {a.order_id!r}; run order-check first")
        mid, o = st.orders[a.order_id]
        o.shipped, o.returnable, o.paid_by_card = a.shipped, not a.not_returnable, not a.not_card
        case = st.desk.open(st.mandates[mid], o)
        print(f"{case.case_id}: recover ${case.refund:,.2f} via {case.path}")
        for v in case.violations:
            print(f"  [{v.severity}] {v.rule}: {v.detail}")
    elif c == "claim-advance":
        if a.case_id not in st.desk.cases:
            raise DeskError(f"no case {a.case_id!r}")
        case = st.desk.advance(a.case_id, a.event)
        print(f"{case.case_id} is now {case.state} (path {case.path}, refund ${case.refund:,.2f})")
    elif c == "refund":
        if a.case_id not in st.desk.cases:
            raise DeskError(f"no case {a.case_id!r}")
        case = st.desk.cases[a.case_id]
        if case.state == "opened":
            raise DeskError(
                f"{case.case_id}: contact the merchant first (claim-advance {case.case_id} contact_merchant)"
            )
        res = stripe_refund(case, a.payment_intent, a.reason)
        case.history.append(("stripe_refund", f"{res['id']} {res.get('status', '?')}"))
        if res.get("status") in ("succeeded", "pending"):
            event = "pay" if case.state == "escalated" else "merchant_resolved"
            st.desk.advance(case.case_id, event)
        print(
            f"{case.case_id}: Stripe refund {res['id']} for ${case.refund:,.2f} is {res.get('status')}; "
            f"case is {case.state}"
        )
        return 0 if res.get("status") in ("succeeded", "pending") else 1
    elif c == "cases":
        for case in st.desk.cases.values():
            print(f"{case.case_id}  {case.state:<19}{case.path:<17}${case.refund:>9,.2f}  {case.order.title}")
        if not st.desk.cases:
            print("no cases yet")
        print(f"protection fund paid out: ${st.desk.fund_paid:,.2f}")
    else:
        for mid, m in st.mandates.items():
            cap = f"max ${m.max_total:,.2f}" if m.max_total is not None else "no total cap"
            print(f"{mid:<14}{m.quantity} x {m.description}  ({cap})")
        if not st.mandates:
            print("no mandates yet")
    return 0
