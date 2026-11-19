"""Stripe refunds for cases (request shape from Stripe's Refunds API; no network)."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from agent_buyer_protection.__main__ import main
from agent_buyer_protection.refunds import RefundError


class FakeStripe:
    def __init__(self, status="succeeded"):
        self.status, self.calls = status, []

    def __call__(self, url, key, form, idem):
        self.calls.append((url, key, form, idem))
        return {"id": "re_123", "object": "refund", "status": self.status, "amount": int(form["amount"])}


class RefundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "p.json")
        self.env = mock.patch.dict(os.environ, {"REFUNDS_STRIPE_KEY": "sk_test_merchant"})
        self.env.start()
        self.net = mock.patch("urllib.request.urlopen", side_effect=AssertionError("tests must not touch the network"))
        self.net.start()
        self.r("mandate-add", "shoes", "--description", "trail shoes", "--keywords", "trail", "--max-total", "130")
        self.r(
            "order-check",
            "shoes",
            "--order-id",
            "o1",
            "--merchant",
            "RunCo",
            "--title",
            "Road Sandal",
            "--unit-price",
            "90",
        )
        self.r("claim-open", "o1", "--shipped")

    def tearDown(self):
        self.net.stop()
        self.env.stop()
        self.tmp.cleanup()

    def r(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([*argv, "--store", self.store])
        return code, out.getvalue()

    def test_refund_after_contacting_the_merchant(self):
        fake = FakeStripe()
        with mock.patch("agent_buyer_protection.refunds._post", fake):
            code, out = self.r("refund", "CASE-0001", "--payment-intent", "pi_3AbCdEf")
            self.assertEqual(code, 1)  # the merchant must be contacted first
            self.assertIn("contact the merchant first", out)
            self.r("claim-advance", "CASE-0001", "contact_merchant")
            code, out = self.r("refund", "CASE-0001", "--payment-intent", "pi_3AbCdEf")
        self.assertEqual(code, 0, out)
        self.assertIn("re_123", out)
        self.assertIn("case is resolved", out)
        url, key, form, idem = fake.calls[0]
        self.assertEqual(url, "https://api.stripe.com/v1/refunds")
        self.assertEqual(key, "sk_test_merchant")
        self.assertEqual(
            (form["payment_intent"], form["amount"], form["metadata[case_id]"]), ("pi_3AbCdEf", "9000", "CASE-0001")
        )
        self.assertEqual(idem, "agent-buyer-protection-CASE-0001-9000")
        with mock.patch("agent_buyer_protection.refunds._post", fake):
            code, out = self.r("refund", "CASE-0001", "--payment-intent", "pi_3AbCdEf")
        self.assertEqual(code, 1)  # already resolved: no second refund
        self.assertEqual(len(fake.calls), 1)
        _, out = self.r("cases")
        self.assertIn("resolved", out)

    def test_escalated_case_is_paid_and_failure_leaves_it_open(self):
        self.r("claim-advance", "CASE-0001", "contact_merchant")
        self.r("claim-advance", "CASE-0001", "no_response")
        with mock.patch("agent_buyer_protection.refunds._post", FakeStripe("failed")):
            code, out = self.r("refund", "CASE-0001", "--payment-intent", "ch_3AbCdEf")
        self.assertEqual(code, 1)
        self.assertIn("is escalated", out.replace("case is escalated", "is escalated"))
        with mock.patch("agent_buyer_protection.refunds._post", FakeStripe()):
            code, out = self.r("refund", "CASE-0001", "--payment-intent", "ch_3AbCdEf")
        self.assertIn("case is paid", out)

    def test_refusals(self):
        self.r("claim-advance", "CASE-0001", "contact_merchant")
        with mock.patch.dict(os.environ, {"REFUNDS_STRIPE_KEY": ""}):
            self.assertIn("REFUNDS_STRIPE_KEY", self.r("refund", "CASE-0001", "--payment-intent", "pi_3AbCdEf")[1])
        self.assertEqual(self.r("refund", "CASE-0001", "--payment-intent", "not-a-payment")[0], 1)
        self.assertEqual(self.r("refund", "CASE-0099", "--payment-intent", "pi_3AbCdEf")[0], 1)
        self.assertTrue(issubclass(RefundError, ValueError))


if __name__ == "__main__":
    unittest.main()
