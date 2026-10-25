import argparse
import csv
import os
import sys
from datetime import date

from .commands import add_commands, run
from .core import ClaimDesk, Mandate, Order, check, decide


def demo():
    m = Mandate(
        "size 10 black running shoes under $120",
        keywords=["running", "shoe"],
        attributes={"size": "10", "color": "black"},
        max_unit_price=120,
        quantity=1,
        merchant_deny=["cheap-kicks.biz"],
        deliver_by=date(2026, 11, 1),
    )
    good = Order(
        "o1", "runshop.com", "Men's Running Shoe", 109, 1, {"size": "10", "color": "black"}, eta=date(2026, 10, 28)
    )
    bad = Order(
        "o2",
        "cheap-kicks.biz",
        "Leather Loafer Shoe",
        113.33,
        3,
        {"size": "1", "color": "brown"},
        shipped=True,
        returnable=False,
    )
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


def build_parser():
    ap = argparse.ArgumentParser(prog="agent-buyer-protection")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    add_commands(sub)
    return ap


def _run(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd != "demo":
        return run(a)
    demo()
    return 0


def main(argv=None):
    """Run the CLI; a bad input file or argument exits 2 with a one-line error instead of a traceback.

    Set AGENT_ECONOMY_DEBUG=1 to see the full traceback.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        return _run(argv)
    except (OSError, ValueError, KeyError, csv.Error) as e:
        if os.environ.get("AGENT_ECONOMY_DEBUG"):
            raise
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"error: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
