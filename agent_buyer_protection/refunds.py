"""Pay a case's refund through Stripe on the original payment.

For the business that took the payment (a merchant, or a platform charging on Stripe): `refund CASE
--payment-intent pi_...` refunds the case's amount on that payment. REFUNDS_STRIPE_KEY must be the key of the
Stripe account that made the charge. The Stripe idempotency key is derived from the case, so retrying after a
timeout can never refund twice, and a case that is already resolved or paid is refused before any call.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

PI_RE = re.compile(r"^(pi|ch)_[A-Za-z0-9]{6,}$")
REASONS = ("requested_by_customer", "duplicate", "fraudulent")


class RefundError(ValueError):
    pass


def _post(url: str, key: str, form: dict, idempotency_key: str) -> dict:
    auth = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": f"Basic {auth}", "Idempotency-Key": idempotency_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            try:
                msg = json.loads(e.read()).get("error", {}).get("message", "")
            except ValueError:
                msg = ""
        raise RefundError(f"Stripe refused the refund ({e.code}): {msg or 'no detail'}") from None
    except (urllib.error.URLError, OSError) as e:
        raise RefundError(f"could not reach Stripe: {e}; it is safe to run the same refund again") from None


def stripe_refund(case, payment: str, reason: str = "requested_by_customer", key: str | None = None, post=None) -> dict:
    key = key if key is not None else os.environ.get("REFUNDS_STRIPE_KEY", "")
    if not key.startswith(("sk_", "rk_")):
        raise RefundError("set REFUNDS_STRIPE_KEY to the secret key of the Stripe account that took the payment")
    if not PI_RE.match(payment or ""):
        raise RefundError("--payment-intent must be a Stripe PaymentIntent (pi_...) or charge (ch_...) id")
    if reason not in REASONS:
        raise RefundError(f"reason must be one of {REASONS}")
    if case.state in ("resolved", "paid"):
        raise RefundError(f"{case.case_id} is already {case.state}; nothing to refund")
    cents = round(case.refund * 100)
    if cents <= 0:
        raise RefundError(f"{case.case_id} has no refund amount")
    form = {
        "payment_intent" if payment.startswith("pi_") else "charge": payment,
        "amount": str(cents),
        "reason": reason,
        "metadata[case_id]": case.case_id,
        "metadata[order_id]": case.order.order_id,
    }
    res = (post or _post)(
        "https://api.stripe.com/v1/refunds", key, form, f"agent-buyer-protection-{case.case_id}-{cents}"
    )
    if res.get("object") != "refund" or not res.get("id"):
        raise RefundError(f"unexpected answer from Stripe: {str(res)[:200]}")
    return res
