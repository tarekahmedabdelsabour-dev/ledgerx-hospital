import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, nowdate

from ledgerx_hospital import billing, data
from ledgerx_hospital.engine import claims
from ledgerx_hospital.engine.money import cents, money


class InsuranceClaim(Document):
	def validate(self):
		if self.to_date and self.from_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("The end date is before the start date"))
		seen = set()
		for ln in self.lines:
			if ln.bill in seen:
				frappe.throw(_("Row {0}: bill {1} is on the claim twice").format(ln.idx, ln.bill))
			seen.add(ln.bill)
			b = frappe.db.get_value("Hospital Bill", ln.bill, ["docstatus", "insurer_invoice", "insurer_total", "insurance_plan", "patient", "posting_date", "branch", "claim"], as_dict=1)
			if not b or b.docstatus != 1 or not b.insurer_invoice:
				frappe.throw(_("Row {0}: bill {1} must be submitted and have an insurer invoice").format(ln.idx, ln.bill))
			if frappe.db.get_value("Hospital Insurance Plan", b.insurance_plan, "insurance_company") != self.insurance_company:
				frappe.throw(_("Row {0}: bill {1} belongs to another insurance company").format(ln.idx, ln.bill))
			if b.claim and b.claim != self.name:
				frappe.throw(_("Row {0}: bill {1} is already on claim {2}").format(ln.idx, ln.bill, b.claim))
			if self.branch and b.branch != self.branch:
				frappe.throw(_("Row {0}: bill {1} belongs to another branch").format(ln.idx, ln.bill))
			ln.patient, ln.posting_date, ln.invoice, ln.amount = b.patient, b.posting_date, b.insurer_invoice, flt(b.insurer_total)
			ln.paid_amount = billing.invoice_paid(ln.invoice)
			if flt(ln.rejected_amount) < 0 or cents(ln.rejected_amount) + cents(ln.paid_amount) > cents(ln.amount):
				frappe.throw(_("Row {0}: rejected plus paid is more than the claimed amount").format(ln.idx))
		self.refresh_totals()

	def refresh_totals(self):
		self.total_amount = money(sum(cents(l.amount) for l in self.lines))
		self.rejected_total = money(sum(cents(l.rejected_amount) for l in self.lines))
		self.paid_total = money(sum(cents(l.paid_amount) for l in self.lines))
		self.outstanding = claims.outstanding(self.total_amount, self.paid_total, self.rejected_total)
		if self.status != "Draft" or self.submitted_on:
			self.status = claims.claim_status(self.total_amount, self.paid_total, self.rejected_total, bool(self.submitted_on))

	def on_update(self):
		for ln in self.lines:
			frappe.db.set_value("Hospital Bill", ln.bill, "claim", self.name, update_modified=False)
		keep = [l.bill for l in self.lines]
		q = "UPDATE `tabHospital Bill` SET claim = NULL WHERE claim = %s"
		if keep:
			q += " AND name NOT IN %s"
			frappe.db.sql(q, (self.name, tuple(keep)))
		else:
			frappe.db.sql(q, (self.name,))

	def on_trash(self):
		if self.status != "Draft":
			frappe.throw(_("Only a draft claim can be deleted"))
		frappe.db.sql("UPDATE `tabHospital Bill` SET claim = NULL WHERE claim = %s", self.name)

	@frappe.whitelist()
	def load_bills(self):
		"""Adds every submitted bill of this insurer in the period that is not on a claim yet."""
		self.check_draft()
		rows = frappe.db.sql("""SELECT b.name FROM `tabHospital Bill` b INNER JOIN `tabHospital Insurance Plan` p ON p.name = b.insurance_plan
			WHERE b.docstatus = 1 AND b.insurer_invoice IS NOT NULL AND b.insurer_invoice != '' AND IFNULL(b.claim, '') = '' AND p.insurance_company = %s
			AND b.posting_date BETWEEN %s AND %s {br} ORDER BY b.posting_date, b.name""".format(br="AND b.branch = %s" if self.branch else ""),
			tuple([self.insurance_company, self.from_date, self.to_date] + ([self.branch] if self.branch else [])))
		have = {l.bill for l in self.lines}
		for (name,) in rows:
			if name not in have:
				self.append("lines", {"bill": name})
		if not self.lines:
			frappe.throw(_("No unclaimed bills for this insurer in the period"))
		self.validate()
		return self.as_dict()

	def check_draft(self):
		if self.status != "Draft":
			frappe.throw(_("The claim was already sent. Only a draft can be changed this way."))

	@frappe.whitelist()
	def submit_claim(self):
		frappe.has_permission("Insurance Claim", "write", self, throw=True)
		self.check_draft()
		if not self.lines:
			frappe.throw(_("The claim has no bills"))
		days = cint(frappe.db.get_value("Hospital Insurer", self.insurance_company, "claim_days")) or 30
		self.submitted_on = nowdate()
		self.due_date = add_days(self.submitted_on, days)
		self.save()
		return self.status

	def _open(self, ln):
		return claims.outstanding(ln.amount, ln.paid_amount, ln.rejected_amount)

	@frappe.whitelist()
	def register_payment(self, amount, mode_of_payment, reference_no=None, posting_date=None):
		"""A payment from the insurer, spread over the claim's invoices oldest first."""
		frappe.has_permission("Insurance Claim", "write", self, throw=True)
		if self.status == "Draft":
			frappe.throw(_("Send the claim first"))
		amount = flt(amount)
		if amount <= 0:
			frappe.throw(_("The amount must be more than zero"))
		open_rows = [{"name": l.name, "due": getdate(l.posting_date), "open": self._open(l)} for l in self.lines]
		spread, left = claims.spread_payment(open_rows, amount)
		if cents(left) > 0:
			frappe.throw(_("The payment is {0} more than the claim's open balance").format(left))
		by = {l.name: l for l in self.lines}
		refs = []
		for name, applied in spread:
			ln = by[name]
			si = frappe.db.get_value("Sales Invoice", ln.invoice, ["outstanding_amount", "grand_total"], as_dict=1)
			if cents(applied) > cents(si.outstanding_amount):
				frappe.throw(_("Invoice {0} has only {1} outstanding").format(ln.invoice, si.outstanding_amount))
			refs.append((ln.invoice, applied, flt(si.outstanding_amount), flt(si.grand_total)))
		pe = billing.pay_insurer_invoices(data.company_of(self.branch) if self.branch else frappe.db.get_single_value("Hospital Settings", "company"), self.branch or self._any_branch(),
			data.insurer_customer_of(self.insurance_company), refs, amount, mode_of_payment, reference_no or self.name, posting_date)
		for name, applied in spread:
			by[name].paid_amount = money(cents(by[name].paid_amount) + cents(applied))
		self.save()
		for ln in self.lines:
			billing.refresh(ln.bill)
		return pe

	def _any_branch(self):
		return self.lines[0] and frappe.db.get_value("Hospital Bill", self.lines[0].bill, "branch")

	@frappe.whitelist()
	def reject_line(self, row, amount, reason):
		"""Records what the insurer refused on one bill. The refused part is written off when a write-off account is set in Hospital Settings."""
		frappe.has_permission("Insurance Claim", "write", self, throw=True)
		ln = next((l for l in self.lines if l.name == row), None)
		if not ln:
			frappe.throw(_("Row not found"))
		if ln.writeoff_entry:
			frappe.throw(_("This rejection was already written off. Cancel the write-off entry first."))
		amount = flt(amount)
		if amount <= 0 or cents(amount) > cents(self._open(ln)):
			frappe.throw(_("The rejected amount must be more than zero and not more than {0}").format(self._open(ln)))
		if not reason:
			frappe.throw(_("Enter the reason the insurer gave"))
		ln.rejected_amount, ln.rejection_reason = amount, reason
		acct = data.settings().claim_writeoff_account
		if acct:
			branch = frappe.db.get_value("Hospital Bill", ln.bill, "branch")
			je = billing.writeoff_entry(data.company_of(branch), branch, data.insurer_customer_of(self.insurance_company), ln.invoice, amount, acct, nowdate(),
				_("Rejected by insurer on claim {0}: {1}").format(self.name, reason))
			ln.writeoff_entry = je
		self.save()
		for l in self.lines:
			billing.refresh(l.bill)
		return self.status
