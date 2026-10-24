import argparse
import sys
from datetime import date

from .core import ClaimDesk, Mandate, Order, check, decide


def demo():
    m = Mandate("size 10 black running shoes under $120", keywords=["running", "shoe"],
                attributes={"size": "10", "color": "black"}, max_unit_price=120, quantity=1,
                merchant_deny=["cheap-kicks.biz"], deliver_by=date(2026, 11, 1))
    good = Order("o1", "runshop.com", "Men's Running Shoe", 109, 1, {"size": "10", "color": "black"}, eta=date(2026, 10, 28))
    bad = Order("o2", "cheap-kicks.biz", "Leather Loafer Shoe", 113.33, 3, {"size": "1", "color": "brown"}, shipped=True, returnable=False)
    for o in (good, bad):
        vs = check(m, o)
        print(f"{o.order_id} {o.title!r} ${o.total:.2f}: {decide(vs).upper()}")
        for v in vs:
            print(f"   [{v.severity}] {v.rule}: {v.detail}")
    desk = ClaimDesk()
    case = desk.open(m, bad)
    print(f"\n{case.case_id}: path={case.path}, refund=${case.refund:.2f}")
    for ev in ("contact_merchant", "merchant_refused", "pay"):
        desk.advance(case.case_id, ev)
        print(f"   {ev} -> {case.state} (path {case.path})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent-buyer-protection")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    ap.parse_args(argv)
    demo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
