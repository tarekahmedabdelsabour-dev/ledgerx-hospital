"""Who pays what on a bill: the insurer's share and the patient's share of every line.

Order of the rules (documented to the users):
  1. Each line finds its rule: a rule for that exact service wins over a rule for its service type, which wins over the plan default.
  2. A rule marked Excluded, or Needs Approval without an approval, leaves the whole line to the patient.
  3. Insurer share = coverage % of the line, never more than the line cap, never leaving the patient less than the fixed co-pay of the line.
  4. Patient cap: what the patient pays on covered lines is limited to the cap; the excess moves to the insurer.
  5. Visit co-pay: the patient pays at least this amount on the bill; the difference is taken back from the insurer.
  6. Annual limit: the insurer never pays more than what is left of the member's limit; the rest goes to the patient.
Credit lines (negative amounts, e.g. returned medicine) use only the coverage % of their rule.
Always: insurer + patient == amount for every line, and 0 <= insurer <= amount for positive lines.
"""
from ledgerx_hospital.engine.money import cents, money, pct_of


def find_rule(rules, service, service_type):
	"""The most specific rule: same service, else same service type, else None. Among equals the first wins."""
	best, best_rank = None, -1
	for r in rules or []:
		svc, typ = r.get("service") or None, r.get("service_type") or None
		if svc and svc != service:
			continue
		if typ and typ != service_type:
			continue
		rank = (2 if svc else 0) + (1 if typ else 0)
		if not svc and not typ:
			continue  # a rule with neither is not a rule
		if rank > best_rank:
			best, best_rank = r, rank
	return best


def split_bill(lines, plan=None, annual_remaining=None):
	"""lines: [{amount, service, service_type, approved}] -> {lines: [{insurer, patient, reason}], insurer, patient, gross}. Amounts are floats in, floats out."""
	amounts = [cents(l.get("amount")) for l in lines]
	n = len(lines)
	ins = [0] * n
	reasons = [""] * n
	covered = [False] * n
	if plan:
		default_pct = float(plan.get("cover_pct") or 0)
		for i, l in enumerate(lines):
			a = amounts[i]
			rule = find_rule(plan.get("rules"), l.get("service"), l.get("service_type"))
			pct = default_pct
			if rule:
				if rule.get("excluded"):
					reasons[i] = "Excluded"
					continue
				if rule.get("requires_approval") and not l.get("approved"):
					reasons[i] = "Needs approval"
					continue
				if rule.get("cover_pct") not in (None, ""):
					pct = float(rule["cover_pct"])
			if a == 0:
				continue
			share = pct_of(a, pct)
			if a > 0:
				if rule and rule.get("line_cap"):
					share = min(share, cents(rule["line_cap"]))
				if rule and rule.get("copay_fixed"):
					share = min(share, max(a - cents(rule["copay_fixed"]), 0))
				share = max(min(share, a), 0)
			ins[i], covered[i] = share, share != 0 or pct > 0
			if share == 0 and pct > 0:
				reasons[i] = "Covered at zero"
		cap = plan.get("patient_cap")
		if cap not in (None, "", 0):
			cap_c = cents(cap)
			pat_cov = sum(amounts[i] - ins[i] for i in range(n) if covered[i] and amounts[i] > 0)
			extra = pat_cov - cap_c
			for i in range(n):
				if extra <= 0:
					break
				if covered[i] and amounts[i] > 0:
					room = amounts[i] - ins[i]
					move = min(room, extra)
					ins[i] += move
					extra -= move
		vc = cents(plan.get("visit_copay"))
		if vc > 0:
			patient_total = sum(amounts) - sum(ins)
			need = vc - patient_total
			for i in range(n):
				if need <= 0:
					break
				if ins[i] > 0:
					take = min(ins[i], need)
					ins[i] -= take
					need -= take
		if annual_remaining is not None:
			over = sum(ins) - max(cents(annual_remaining), 0)
			for i in range(n - 1, -1, -1):
				if over <= 0:
					break
				if ins[i] > 0:
					take = min(ins[i], over)
					ins[i] -= take
					over -= take
	out = []
	for i in range(n):
		out.append({"insurer": money(ins[i]), "patient": money(amounts[i] - ins[i]), "reason": reasons[i]})
	return {"lines": out, "insurer": money(sum(ins)), "patient": money(sum(amounts) - sum(ins)), "gross": money(sum(amounts))}


def line_net(price, qty, discount_pct=0):
	"""Price x qty less the discount, in money (rounded to the cent)."""
	gross = cents(price) * float(qty or 0)
	return money(cents(round(gross) / 100.0 * (1 - float(discount_pct or 0) / 100.0)))
