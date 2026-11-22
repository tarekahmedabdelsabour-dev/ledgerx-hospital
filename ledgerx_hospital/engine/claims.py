"""Insurance claims: status, ageing and how a payment is spread. Amounts are floats in and out, summed in cents."""
from datetime import date

from ledgerx_hospital.engine.money import cents, money

BUCKETS = [(30, "0-30"), (60, "31-60"), (90, "61-90"), (120, "91-120"), (None, "120+")]


def aging_bucket(days):
	d = max(int(days), 0)
	for limit, name in BUCKETS:
		if limit is None or d <= limit:
			return name


def claim_status(total, paid, rejected, submitted):
	"""Draft -> Submitted -> Partially Paid -> Paid (or Rejected when nothing was paid and everything was refused)."""
	if not submitted:
		return "Draft"
	t, p, r = cents(total), cents(paid), cents(rejected)
	if t > 0 and p + r >= t:
		return "Paid" if p > 0 else "Rejected"
	if p > 0 or r > 0:
		return "Partially Paid"
	return "Submitted"


def outstanding(total, paid, rejected):
	return money(max(cents(total) - cents(paid) - cents(rejected), 0))


def spread_payment(lines, amount):
	"""Pay the oldest lines first. lines: [{name, due (date), open (amount still unpaid)}] -> ([(name, applied)], unapplied)."""
	left = cents(amount)
	out = []
	for l in sorted(lines, key=lambda x: (x.get("due") or date.max, str(x.get("name")))):
		if left <= 0:
			break
		take = min(left, max(cents(l.get("open")), 0))
		if take:
			out.append((l["name"], money(take)))
			left -= take
	return out, money(left)


def days_overdue(due, today):
	return (today - due).days if due else 0
