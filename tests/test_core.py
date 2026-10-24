import unittest
from datetime import date

from agent_buyer_protection import ClaimDesk, Mandate, Order, check, decide

M = Mandate(
    "shoes",
    keywords=["running"],
    attributes={"size": "10"},
    max_unit_price=100,
    quantity=1,
    merchant_allow=["a.com"],
    deliver_by=date(2026, 11, 1),
)


class Tests(unittest.TestCase):
    def test_allow(self):
        o = Order("1", "a.com", "Running shoe", 90, 1, {"size": "10"}, eta=date(2026, 10, 30))
        self.assertEqual(decide(check(M, o)), "allow")

    def test_soft_violation_needs_human(self):
        o = Order("1", "b.com", "Running shoe", 90, 1, {"size": "10"}, eta=date(2026, 11, 5))
        rules = {v.rule for v in check(M, o)}
        self.assertEqual(rules, {"merchant_unapproved", "late_delivery"})
        self.assertEqual(decide(check(M, o)), "confirm_with_human")

    def test_block_and_full_refund_for_wrong_item(self):
        o = Order("1", "a.com", "Loafer", 90, 1, {"size": "1"}, shipped=True)
        self.assertEqual(decide(check(M, o)), "block")
        case = ClaimDesk().open(M, o)
        self.assertEqual(case.path, "merchant_return")
        self.assertEqual(case.refund, 90)

    def test_partial_refund_for_overspend_and_quantity(self):
        o = Order("1", "a.com", "Running shoe", 130, 3, {"size": "10"})
        case = ClaimDesk().open(M, o)
        self.assertEqual(case.path, "cancel")
        self.assertEqual(case.refund, 2 * 130 + 30)

    def test_escalation_to_fund_with_cap(self):
        desk = ClaimDesk(fund_limit_per_claim=50)
        o = Order("1", "a.com", "Loafer", 90, 1, {"size": "10"}, shipped=True, returnable=False, paid_by_card=False)
        c = desk.open(M, o)
        self.assertEqual(c.path, "protection_fund")
        desk.advance(c.case_id, "contact_merchant")
        desk.advance(c.case_id, "no_response")
        desk.advance(c.case_id, "pay")
        self.assertEqual((c.state, c.refund, desk.fund_paid), ("paid", 50, 50))
        with self.assertRaises(ValueError):
            desk.advance(c.case_id, "pay")


if __name__ == "__main__":
    unittest.main()
