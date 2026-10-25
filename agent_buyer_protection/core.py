"""Mandate checks for agent purchases and a claims workflow when they go wrong."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date

__all__ = ["Mandate", "Order", "Violation", "check", "decide", "ClaimDesk", "Case"]


@dataclass
class Mandate:
    description: str
    keywords: list = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    max_unit_price: float | None = None
    max_total: float | None = None
    quantity: int = 1
    merchant_allow: list = field(default_factory=list)
    merchant_deny: list = field(default_factory=list)
    deliver_by: date | None = None


@dataclass
class Order:
    order_id: str
    merchant: str
    title: str
    unit_price: float
    quantity: int
    attributes: dict = field(default_factory=dict)
    shipping: float = 0.0
    eta: date | None = None
    shipped: bool = False
    returnable: bool = True
    paid_by_card: bool = True

    @property
    def total(self):
        return self.unit_price * self.quantity + self.shipping


@dataclass
class Violation:
    rule: str
    severity: str  # high / medium / low
    detail: str


def _merchant(name: str) -> str:
    return " ".join(str(name).split()).casefold()


def check(m: Mandate, o: Order) -> list[Violation]:
    v = []
    numbers = {"unit_price": o.unit_price, "shipping": o.shipping, "quantity": o.quantity}
    bad = {k: x for k, x in numbers.items() if not (isinstance(x, (int, float)) and math.isfinite(x) and x >= 0)}
    if bad or o.quantity < 1:
        # nan sails past every `>` cap and negatives shrink the total under it, so never trust them
        v.append(Violation("invalid_order", "high", f"non-finite, negative or zero values: {bad or numbers}"))
        return v
    title = o.title.lower()
    missing = [k for k in m.keywords if k.lower() not in title]
    if missing:
        v.append(Violation("wrong_item", "high", f"title missing {missing}: {o.title!r}"))
    for key, want in m.attributes.items():
        got = o.attributes.get(key)
        if got is None:
            v.append(Violation("attribute_unknown", "medium", f"{key} not specified (wanted {want})"))
        elif str(got).lower() != str(want).lower():
            v.append(Violation("attribute_mismatch", "high", f"{key}: wanted {want}, got {got}"))
    if o.quantity != m.quantity:
        v.append(
            Violation(
                "quantity",
                "high" if o.quantity > m.quantity else "medium",
                f"wanted {m.quantity}, ordering {o.quantity}",
            )
        )
    if m.max_unit_price is not None and o.unit_price > m.max_unit_price:
        v.append(Violation("unit_price", "high", f"${o.unit_price:.2f} > cap ${m.max_unit_price:.2f}"))
    if m.max_total is not None and o.total > m.max_total:
        v.append(Violation("total", "high", f"total ${o.total:.2f} > cap ${m.max_total:.2f}"))
    if m.merchant_deny and _merchant(o.merchant) in {_merchant(x) for x in m.merchant_deny}:
        v.append(Violation("merchant_denied", "high", o.merchant))
    if m.merchant_allow and _merchant(o.merchant) not in {_merchant(x) for x in m.merchant_allow}:
        v.append(Violation("merchant_unapproved", "medium", f"{o.merchant} not in allow list"))
    if m.deliver_by and o.eta and o.eta > m.deliver_by:
        v.append(Violation("late_delivery", "medium", f"eta {o.eta} after {m.deliver_by}"))
    return v


def decide(violations: list[Violation]) -> str:
    if any(x.severity == "high" for x in violations):
        return "block"
    if violations:
        return "confirm_with_human"
    return "allow"


@dataclass
class Case:
    case_id: str
    order: Order
    violations: list
    path: str
    refund: float
    state: str = "opened"
    history: list = field(default_factory=list)


FLOW = {
    "opened": {"contact_merchant": "merchant_contacted"},
    "merchant_contacted": {
        "merchant_resolved": "resolved",
        "merchant_refused": "escalated",
        "no_response": "escalated",
    },
    "escalated": {"pay": "paid"},
    "resolved": {},
    "paid": {},
}


class ClaimDesk:
    def __init__(self, fund_limit_per_claim: float = 500.0):
        self.fund_limit = fund_limit_per_claim
        self.cases: dict[str, Case] = {}
        self._ids = itertools.count(1)
        self.fund_paid = 0.0

    @staticmethod
    def refund_amount(m: Mandate, o: Order, violations: list[Violation]) -> float:
        rules = {x.rule for x in violations}
        if "invalid_order" in rules:
            return 0.0  # nothing trustworthy to refund against; a human reviews it
        if rules & {"wrong_item", "attribute_mismatch", "merchant_denied"}:
            return round(o.total, 2)  # whole order is wrong
        refund = 0.0
        if "quantity" in rules and o.quantity > m.quantity:
            refund += (o.quantity - m.quantity) * o.unit_price
        if "unit_price" in rules and m.max_unit_price is not None:
            refund += (o.unit_price - m.max_unit_price) * min(o.quantity, m.quantity)
        if "total" in rules and m.max_total is not None and not refund:
            refund = o.total - m.max_total
        return round(refund, 2)

    def open(self, m: Mandate, o: Order) -> Case:
        violations = check(m, o)
        if not violations:
            raise ValueError("order matches mandate; nothing to claim")
        if not o.shipped:
            path = "cancel"
        elif o.returnable:
            path = "merchant_return"
        elif o.paid_by_card:
            path = "chargeback"
        else:
            path = "protection_fund"
        case = Case(f"CASE-{next(self._ids):04d}", o, violations, path, self.refund_amount(m, o, violations))
        case.history.append(("opened", path))
        self.cases[case.case_id] = case
        return case

    def advance(self, case_id: str, event: str) -> Case:
        c = self.cases[case_id]
        nxt = FLOW[c.state].get(event)
        if not nxt:
            raise ValueError(f"event {event!r} invalid in state {c.state!r}")
        if nxt == "escalated":
            c.path = "chargeback" if c.order.paid_by_card else "protection_fund"
        if nxt == "paid":
            payout = min(c.refund, self.fund_limit) if c.path == "protection_fund" else c.refund
            c.refund = payout
            if c.path == "protection_fund":
                self.fund_paid += payout
        c.state = nxt
        c.history.append((event, nxt))
        return c
