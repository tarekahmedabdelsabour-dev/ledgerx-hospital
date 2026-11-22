"""Doctor fees: which rule applies to a charge and how much the doctor earns. Pure functions."""
from ledgerx_hospital.engine.money import cents, money, pct_of


def pick_rule(rules, service, service_type, payer):
	"""The most specific rule for a charge. Specificity: service (4) > service type (2); then an exact payer (1) beats 'All'.
	A rule applies when each condition it states matches. Ties go to the earlier rule."""
	best, best_rank = None, (-1, -1)
	for idx, r in enumerate(rules or []):
		svc, typ, pay = r.get("service") or None, r.get("service_type") or None, r.get("payer") or "All"
		if svc and svc != service:
			continue
		if typ and typ != service_type:
			continue
		if pay not in ("All", payer):
			continue
		rank = ((4 if svc else 0) + (2 if typ else 0), 1 if pay == payer else 0)
		if rank > best_rank:
			best, best_rank = r, rank
	return best


def doctor_share(amount, qty, rule):
	"""The doctor's money for one charge. Percent is of the net amount; Fixed is per unit. Never more than the amount itself on a positive charge."""
	if not rule:
		return 0.0
	a = cents(amount)
	sign = -1 if a < 0 else 1
	a = abs(a)
	if rule.get("mode") == "Fixed":
		share = cents(rule.get("value")) * abs(float(qty or 1))
		share = int(round(share))
	else:
		share = pct_of(a, float(rule.get("value") or 0))
	share = min(share, a) if a else 0
	return money(sign * share)


def share_for_charge(rules, charge, payer):
	"""charge: {amount, qty, service, service_type} -> (share, rule or None)."""
	rule = pick_rule(rules, charge.get("service"), charge.get("service_type"), payer)
	return doctor_share(charge.get("amount"), charge.get("qty"), rule), rule


def statement_totals(rows, deductions=0):
	"""rows: [{amount, share}] -> (gross, share_total, net after deductions, never below zero)."""
	gross = sum(cents(r.get("amount")) for r in rows)
	share = sum(cents(r.get("share")) for r in rows)
	net = share - cents(deductions)
	return money(gross), money(share), money(max(net, 0))
