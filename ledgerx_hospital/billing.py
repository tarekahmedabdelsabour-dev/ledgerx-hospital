"""Billing: turns unbilled charges into a bill, splits it between insurer and patient, and posts the invoices and payments."""
import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from ledgerx_hospital import data
from ledgerx_hospital.engine import billing as engine
from ledgerx_hospital.engine import commission
from ledgerx_hospital.engine.money import cents, money

NEEDED_CHARGE_FIELDS = ["name", "patient", "status", "bill", "item_code", "description", "service", "service_type", "doctor", "qty", "rate", "amount", "approved",
	"discount_pct", "branch", "posting_date"]


def unbilled(patient, admission=None, branch=None):
	filters = {"patient": patient, "status": "Unbilled"}
	if admission:
		filters["admission"] = admission
	if branch:
		filters["branch"] = branch
	return frappe.get_all("Hospital Charge", filters=filters, fields=NEEDED_CHARGE_FIELDS, order_by="posting_date asc, creation asc")


def _doctor_rules(doctor, cache):
	if doctor not in cache:
		cache[doctor] = [{"service": r.service, "service_type": r.service_type, "payer": r.payer, "mode": r.mode, "value": r.value}
			for r in frappe.get_all("Doctor Fee Rule", filters={"parent": doctor, "parenttype": "Hospital Doctor"}, fields=["service", "service_type", "payer", "mode", "value"], order_by="idx")]
	return cache[doctor]


def compute(bill):
	"""Fills the lines from their charges, splits every line and sets the totals. Safe to run again: it only reads the charges."""
	plan = bill.insurance_plan or None
	if plan:
		data.check_plan_usable(plan, bill.posting_date)
	seen, cache = set(), {}
	lines = []
	for ln in bill.lines:
		if not ln.charge:
			frappe.throw(_("Row {0}: choose a charge. Use Get Unbilled Charges to fill the bill.").format(ln.idx))
		if ln.charge in seen:
			frappe.throw(_("Row {0}: charge {1} is on the bill twice").format(ln.idx, ln.charge))
		seen.add(ln.charge)
		c = frappe.db.get_value("Hospital Charge", ln.charge, NEEDED_CHARGE_FIELDS, as_dict=1)
		if not c:
			frappe.throw(_("Row {0}: charge {1} does not exist").format(ln.idx, ln.charge))
		if c.patient != bill.patient:
			frappe.throw(_("Row {0}: charge {1} belongs to another patient").format(ln.idx, ln.charge))
		if c.status == "Cancelled":
			frappe.throw(_("Row {0}: charge {1} is cancelled").format(ln.idx, ln.charge))
		if c.status == "Billed" and c.bill != bill.name:
			frappe.throw(_("Row {0}: charge {1} is already on bill {2}").format(ln.idx, ln.charge, c.bill))
		for k in ("item_code", "description", "service", "service_type", "doctor", "qty", "rate", "amount"):
			ln.set(k, c.get(k))
		approved = cint(c.approved) or (1 if plan and c.service and data.find_approval(bill.patient, plan, c.service, bill.posting_date) else 0)
		lines.append({"amount": flt(c.amount), "service": c.service, "service_type": c.service_type, "approved": bool(approved)})
	remaining = data.annual_remaining(plan, bill.patient, bill.posting_date, exclude_bill=bill.name) if plan else None
	res = engine.split_bill(lines, data.plan_dict(plan) if plan else None, remaining)
	payer = "Insurance" if plan else "Cash"
	for ln, r in zip(bill.lines, res["lines"]):
		ln.insurer_share, ln.patient_share, ln.reason = r["insurer"], r["patient"], r["reason"]
		ln.doctor_share = 0
		if ln.doctor:
			share, _rule = commission.share_for_charge(_doctor_rules(ln.doctor, cache), {"amount": ln.amount, "qty": ln.qty, "service": ln.service, "service_type": ln.service_type}, payer)
			ln.doctor_share = share
	bill.gross_total, bill.insurer_total, bill.patient_total = res["gross"], res["insurer"], res["patient"]
	bill.annual_remaining = remaining
	return res


# ------------------------------------------------------------------ invoices
def _invoice_rows(bill, party):
	"""[(line, qty, rate, description, share)] of the lines one party pays. Plain qty x price when the share is the whole line, else one unit at the share."""
	out = []
	for ln in bill.lines:
		share = flt(ln.patient_share if party == "patient" else ln.insurer_share)
		if cents(share) == 0:
			continue
		whole = cents(share) == cents(ln.amount) and abs(flt(ln.qty) * flt(ln.rate) - share) < 0.005 and flt(ln.qty) > 0
		if whole:
			out.append((ln, flt(ln.qty), flt(ln.rate), ln.description, share))
		else:
			label = "%s x %s" % (ln.description, flt(ln.qty, 3)) if flt(ln.qty) != 1 else ln.description
			out.append((ln, 1, share, "%s (%s)" % (label, _("insurer share") if party == "insurer" else _("patient share")), share))
	return out


def _make_invoice(bill, party):
	rows = _invoice_rows(bill, party)
	if not rows:
		return None
	b = data.branch_doc(bill.branch)
	s = data.settings()
	si = frappe.new_doc("Sales Invoice")
	si.customer = data.patient_customer(bill.patient) if party == "patient" else data.insurer_customer(bill.insurance_plan)
	si.company = b.company
	si.posting_date = bill.posting_date
	si.set_posting_time = 1
	si.update_stock = 0
	si.selling_price_list = data.cash_price_list(bill.branch) or frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	si.ignore_pricing_rule = 1
	if b.cost_center:
		si.cost_center = b.cost_center
	if party == "patient":
		si.allocate_advances_automatically = 1
	else:
		days = cint(frappe.db.get_value("Hospital Insurer", frappe.db.get_value("Hospital Insurance Plan", bill.insurance_plan, "insurance_company"), "claim_days")) or 30
		si.due_date = add_days(bill.posting_date, days)
	si.hs_bill, si.hs_patient, si.hs_branch = bill.name, bill.patient, bill.branch
	si.remarks = _("Hospital bill {0}").format(bill.name)
	expected = 0.0
	for ln, qty, rate, desc, share in rows:
		row = {"item_code": ln.item_code, "qty": qty, "rate": rate, "price_list_rate": rate, "discount_percentage": 0, "description": desc, "uom": frappe.db.get_value("Item", ln.item_code, "stock_uom")}
		if b.cost_center:
			row["cost_center"] = b.cost_center
		si.append("items", row)
		expected += share
	if s.sales_taxes_template:
		si.taxes_and_charges = s.sales_taxes_template
		si.set_taxes()
	si.insert(ignore_permissions=True)
	if abs(flt(si.net_total) - expected) > 0.01:
		frappe.throw(_("The invoice total ({0}) does not match the bill ({1}). Check pricing rules and item prices, then try again.").format(si.net_total, money(cents(expected))))
	si.submit()
	return si


def post(bill):
	"""On submit: the patient's invoice, the insurer's invoice, and the charges marked Billed."""
	for ln in bill.lines:
		st = frappe.db.get_value("Hospital Charge", ln.charge, ["status", "bill"], as_dict=1)
		if st.status != "Unbilled":
			frappe.throw(_("Charge {0} is no longer unbilled ({1}). Remove it from the bill.").format(ln.charge, st.status))
	if flt(bill.patient_total) < 0 or flt(bill.insurer_total) < 0:
		frappe.throw(_("The bill has a negative total. Settle the credit lines with a credit note instead."))
	pat = _make_invoice(bill, "patient")
	ins = _make_invoice(bill, "insurer") if flt(bill.insurer_total) > 0 else None
	if pat:
		bill.db_set("patient_invoice", pat.name)
	if ins:
		bill.db_set("insurer_invoice", ins.name)
	for ln in bill.lines:
		frappe.db.set_value("Hospital Charge", ln.charge, {"status": "Billed", "bill": bill.name}, update_modified=False)
	refresh(bill.name)


def unpost(bill):
	"""On cancel: both invoices cancelled (insurer first) and the charges released."""
	blocked = frappe.db.sql("""SELECT DISTINCT bl.statement FROM `tabBill Line` bl WHERE bl.parent = %s AND IFNULL(bl.statement, '') != ''""", bill.name)
	if blocked:
		frappe.throw(_("The bill is part of doctor statement {0}. Cancel the statement first.").format(blocked[0][0]))
	claim = frappe.db.sql("""SELECT c.name FROM `tabClaim Line` cl INNER JOIN `tabInsurance Claim` c ON c.name = cl.parent WHERE cl.bill = %s AND c.status != 'Draft'""", bill.name)
	if claim:
		frappe.throw(_("The bill is on claim {0}. Remove it from the claim first.").format(claim[0][0]))
	frappe.db.sql("""DELETE cl FROM `tabClaim Line` cl INNER JOIN `tabInsurance Claim` c ON c.name = cl.parent WHERE cl.bill = %s AND c.status = 'Draft'""", bill.name)
	for fld in ("insurer_invoice", "patient_invoice"):
		name = bill.get(fld)
		if name and frappe.db.get_value("Sales Invoice", name, "docstatus") == 1:
			si = frappe.get_doc("Sales Invoice", name)
			si.flags.ignore_links = True
			si.cancel()
	for ln in bill.lines:
		frappe.db.set_value("Hospital Charge", ln.charge, {"status": "Unbilled", "bill": None}, update_modified=False)


def refresh(name):
	"""Re-reads the patient invoice and stores the balance and status on the bill."""
	b = frappe.db.get_value("Hospital Bill", name, ["docstatus", "patient_invoice", "insurer_invoice", "patient_total", "insurer_total"], as_dict=1)
	if not b:
		return
	if b.docstatus == 2:
		frappe.db.set_value("Hospital Bill", name, "status", "Cancelled", update_modified=False)
		return
	if b.docstatus == 0:
		return
	outstanding, total, applied = 0.0, 0.0, 0.0
	if b.patient_invoice:
		si = frappe.db.get_value("Sales Invoice", b.patient_invoice, ["outstanding_amount", "grand_total"], as_dict=1)
		outstanding, total = flt(si.outstanding_amount), flt(si.grand_total)
		applied = flt(frappe.db.sql("SELECT COALESCE(SUM(allocated_amount), 0) FROM `tabSales Invoice Advance` WHERE parent = %s", b.patient_invoice)[0][0])
	if outstanding < -0.005:
		status = "Credit"
	elif outstanding <= 0.005:
		status = "Paid"
	elif outstanding < total - 0.005:
		status = "Partly Paid"
	else:
		status = "Unpaid"
	frappe.db.set_value("Hospital Bill", name, {"status": status, "patient_outstanding": max(outstanding, 0), "deposits_applied": applied}, update_modified=False)


# ------------------------------------------------------------------ money in
def _cash_account(mode, company):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	acc = get_bank_cash_account(mode, company)
	if not acc or not acc.get("account"):
		frappe.throw(_("Mode of payment {0} has no account for company {1}").format(mode, company))
	return acc["account"]


def _payment_entry(company, branch, customer, amount, mode, reference_no, posting_date, references=None):
	from erpnext.accounts.party import get_party_account

	cur = frappe.get_cached_value("Company", company, "default_currency")
	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.company = company
	pe.posting_date = posting_date or nowdate()
	pe.mode_of_payment = mode
	pe.party_type = "Customer"
	pe.party = customer
	pe.paid_from = get_party_account("Customer", customer, company)
	pe.paid_to = _cash_account(mode, company)
	pe.paid_from_account_currency = pe.paid_to_account_currency = cur
	pe.paid_amount = pe.received_amount = amount
	pe.source_exchange_rate = pe.target_exchange_rate = 1
	pe.reference_no = reference_no or ""
	pe.reference_date = pe.posting_date
	cc = data.branch_doc(branch).cost_center
	if cc:
		pe.cost_center = cc
	for ref in references or []:
		pe.append("references", ref)
	pe.insert(ignore_permissions=True)
	pe.submit()
	return pe


def receive_payment(bill_name, amount, mode_of_payment, reference_no=None, posting_date=None):
	"""A payment from the patient against the bill's patient invoice."""
	bill = frappe.get_doc("Hospital Bill", bill_name)
	if bill.docstatus != 1 or not bill.patient_invoice:
		frappe.throw(_("Submit the bill first"))
	amount = flt(amount)
	si = frappe.get_doc("Sales Invoice", bill.patient_invoice)
	if amount <= 0:
		frappe.throw(_("The amount must be more than zero"))
	if amount > flt(si.outstanding_amount) + 0.005:
		frappe.throw(_("The patient owes {0}. Receive a deposit for more than that.").format(si.outstanding_amount))
	pe = _payment_entry(bill.company, bill.branch, si.customer, amount, mode_of_payment, reference_no or bill.name, posting_date,
		[{"reference_doctype": "Sales Invoice", "reference_name": si.name, "total_amount": si.grand_total, "outstanding_amount": si.outstanding_amount, "allocated_amount": amount}])
	refresh(bill.name)
	return pe.name


def receive_deposit(patient, branch, amount, mode_of_payment, admission=None, reference_no=None, posting_date=None):
	"""An advance from the patient. It stays on the patient's account and is applied to the next invoice automatically."""
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("The amount must be more than zero"))
	customer = data.patient_customer(patient)
	pe = _payment_entry(data.company_of(branch), branch, customer, amount, mode_of_payment, reference_no or admission or patient, posting_date)
	return pe.name


def pay_insurer_invoices(company, branch, insurer_customer, rows, amount, mode, reference_no, posting_date):
	"""A payment from an insurer spread over its invoices. rows: [(invoice, allocated, outstanding, grand_total)]. Anything not allocated stays as an advance."""
	refs = [{"reference_doctype": "Sales Invoice", "reference_name": inv, "total_amount": gt, "outstanding_amount": out, "allocated_amount": alloc} for inv, alloc, out, gt in rows]
	return _payment_entry(company, branch, insurer_customer, amount, mode, reference_no, posting_date, refs).name


def writeoff_entry(company, branch, customer, invoice, amount, account, posting_date, remark):
	"""Journal entry that writes off part of an insurer invoice the insurer refused."""
	from erpnext.accounts.party import get_party_account

	cc = data.branch_doc(branch).cost_center
	common = {"cost_center": cc} if cc else {}
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = posting_date or nowdate()
	je.user_remark = remark
	je.append("accounts", {"account": account, "debit_in_account_currency": amount, **common})
	je.append("accounts", {"account": get_party_account("Customer", customer, company), "party_type": "Customer", "party": customer, "credit_in_account_currency": amount,
		"reference_type": "Sales Invoice", "reference_name": invoice, **common})
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def invoice_paid(invoice):
	"""Money actually received against an invoice: the allocated amounts of submitted payments. Write-offs are not payments."""
	return flt(frappe.db.sql("""SELECT COALESCE(SUM(per.allocated_amount), 0) FROM `tabPayment Entry Reference` per INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE pe.docstatus = 1 AND per.reference_doctype = 'Sales Invoice' AND per.reference_name = %s""", invoice)[0][0])


def is_fully_paid(bill_name):
	"""True when every invoice of the bill has no balance (used by the 'Paid' basis of doctor fees)."""
	b = frappe.db.get_value("Hospital Bill", bill_name, ["patient_invoice", "insurer_invoice"], as_dict=1)
	for inv in (b.patient_invoice, b.insurer_invoice):
		if inv and flt(frappe.db.get_value("Sales Invoice", inv, "outstanding_amount")) > 0.005:
			return False
	return True


def today():
	return getdate(nowdate())
