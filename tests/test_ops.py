import contextlib
import io
import os
import tempfile
import unittest

from agent_buyer_protection.__main__ import main
from agent_buyer_protection.ops import State

MANDATE = ["--description", "trail running shoes", "--keywords", "trail", "shoe", "--attr", "size=10"]
GOOD = ["--merchant", "RunCo", "--title", "Trail Shoe X", "--unit-price", "110", "--attr", "size=10"]


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(list(argv))
    return code, out.getvalue()


class DeskOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "desk.json")
        self.s = ["--store", self.path]
        self.ok("mandate-add", "shoes", *MANDATE, "--max-total", "130")

    def tearDown(self):
        self.tmp.cleanup()

    def ok(self, *argv):
        code, out = run(*argv, *self.s)
        self.assertEqual(code, 0, out)
        return out

    def test_matching_order_is_allowed_and_cannot_be_claimed(self):
        self.assertEqual(self.ok("order-check", "shoes", "--order-id", "o1", *GOOD), "ALLOW\n")
        self.assertEqual(run("claim-open", "o1", *self.s)[0], 1)

    def test_wrong_order_is_blocked_then_recovered_through_the_fund(self):
        bad = ["--merchant", "RunCo", "--title", "Road Sandal", "--unit-price", "900", "--attr", "size=10"]
        code, out = run("order-check", "shoes", "--order-id", "o2", *bad, *self.s)
        self.assertEqual((code, out.splitlines()[0]), (1, "BLOCK"))
        out = self.ok("claim-open", "o2", "--shipped", "--not-returnable", "--not-card")
        self.assertIn("CASE-0001: recover $900.00 via protection_fund", out)
        self.ok("claim-advance", "CASE-0001", "contact_merchant")
        self.ok("claim-advance", "CASE-0001", "merchant_refused")
        self.assertIn("refund $500.00", self.ok("claim-advance", "CASE-0001", "pay"))  # capped by the fund limit
        st = State(self.path)
        self.assertEqual((st.desk.fund_paid, st.desk.cases["CASE-0001"].state), (500.0, "paid"))
        self.assertEqual(run("claim-advance", "CASE-0001", "pay", *self.s)[0], 1)  # never paid twice

    def test_soft_violation_asks_the_human(self):
        self.ok("mandate-add", "gift", "--description", "a mug", "--merchant-allow", "MugShop")
        argv = ["order-check", "gift", "--order-id", "o3", "--merchant", "Other", "--title", "Mug", "--unit-price", "9"]
        code, out = run(*argv, *self.s)
        self.assertEqual((code, out.splitlines()[0]), (1, "CONFIRM_WITH_HUMAN"))

    def test_refusals(self):
        for argv in (
            ["mandate-add", "shoes", *MANDATE],  # duplicate
            ["order-check", "nope", "--order-id", "o", *GOOD],
            ["claim-open", "never-checked"],
            ["claim-advance", "CASE-9999", "pay"],
            ["mandate-add", "m2", "--description", "x", "--deliver-by", "soon"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv, *self.s)[0], 1)


if __name__ == "__main__":
    unittest.main()
