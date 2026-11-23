import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from ledgerx_hospital import billing, data
from ledgerx_hospital.engine import commission
from ledgerx_hospital.engine.money import cents


class DoctorStatement(Document):
	def validate(self):
		self.company = data.company_of(self.branch)
		rows = [{"amount": r.amount, "share": r.share} for r in self.rows]
		self.gross_total, self.share_total, self.net_payable = commission.statement_totals(rows, self.deductions)
		if cents(self.deductions) > cents(self.share_total):
			frappe.throw(_("The deductions are more than the doctor's share"))
		if flt(self.deductions) and not self.deduction_note:
			frappe.throw(_("Explain the deduction"))

	@frappe.whitelist()
	def load_rows(self):
		"""Every submitted bill line of this doctor in the period that is not on another statement. With the 'Paid' basis only bills paid in full count."""
		self.check_draft()
		paid_basis = data.settings().commission_basis == "Paid"
		rows = frappe.db.sql("""SELECT bl.name, bl.parent, bl.description, bl.amount, bl.doctor_share, b.posting_date, b.patient FROM `tabBill Line` bl
			INNER JOIN `tabHospital Bill` b ON b.name = bl.parent WHERE b.docstatus = 1 AND bl.doctor = %s AND b.branch = %s AND b.posting_date BETWEEN %s AND %s
			AND IFNULL(bl.statement, '') = '' AND bl.doctor_share != 0 ORDER BY b.posting_date, b.name, bl.idx""", (self.doctor, self.branch, self.from_date, self.to_date), as_dict=1)
		self.set("rows", [])
		skipped = 0
		for r in rows:
			if paid_basis and not billing.is_fully_paid(r.parent):
				skipped += 1
				continue
			self.append("rows", {"bill": r.parent, "posting_date": r.posting_date, "patient": r.patient, "description": r.description, "amount": r.amount, "share": r.doctor_share, "bill_line": r.name})
		if not self.rows:
			frappe.throw(_("No fees to settle for this doctor in the period"))
		if skipped:
			frappe.msgprint(_("{0} lines were left out because their bills are not paid in full yet.").format(skipped), indicator="orange")
		self.validate()
		return self.as_dict()

	def check_draft(self):
		if self.status != "Draft":
			frappe.throw(_("Only a draft statement can be changed this way."))

	@frappe.whitelist()
	def approve(self):
		frappe.has_permission("Doctor Statement", "write", self, throw=True)
		self.check_draft()
		if not self.rows:
			frappe.throw(_("The statement has no lines"))
		for r in self.rows:
			cur = frappe.db.get_value("Bill Line", r.bill_line, ["statement", "parent"], as_dict=1)
			if not cur or cur.parent != r.bill:
				frappe.throw(_("Row {0}: the bill line no longer exists").format(r.idx))
			if cur.statement and cur.statement != self.name:
				frappe.throw(_("Row {0}: this fee is already on statement {1}").format(r.idx, cur.statement))
			if frappe.db.get_value("Hospital Bill", r.bill, "docstatus") != 1:
				frappe.throw(_("Row {0}: bill {1} is not submitted").format(r.idx, r.bill))
		self.status = "Approved"
		self.posting_date = self.posting_date or nowdate()
		self.save()
		for r in self.rows:
			frappe.db.set_value("Bill Line", r.bill_line, "statement", self.name, update_modified=False)
		return self.status

	@frappe.whitelist()
	def create_payable(self):
		"""A purchase invoice to the doctor's supplier account for the net amount."""
		frappe.has_permission("Doctor Statement", "write", self, throw=True)
		if self.status != "Approved":
			frappe.throw(_("Approve the statement first"))
		if self.purchase_invoice:
			frappe.throw(_("The payable was already created: {0}").format(self.purchase_invoice))
		s = data.settings()
		sup = frappe.db.get_value("Hospital Doctor", self.doctor, "supplier")
		if not sup:
			frappe.throw(_("Set a Supplier on the doctor's card to pay the fees"))
		if not (s.doctor_fee_item and s.doctor_expense_account):
			frappe.throw(_("Set the doctor fee item and the expense account in Hospital Settings"))
		if cents(self.net_payable) <= 0:
			frappe.throw(_("Nothing to pay"))
		cc = data.branch_doc(self.branch).cost_center
		pi = frappe.new_doc("Purchase Invoice")
		pi.supplier, pi.company, pi.posting_date, pi.set_posting_time, pi.update_stock = sup, self.company, self.posting_date or nowdate(), 1, 0
		pi.bill_no = self.name
		pi.append("items", {"item_code": s.doctor_fee_item, "qty": 1, "rate": self.net_payable, "expense_account": s.doctor_expense_account,
			"description": _("Doctor fees {0} to {1}").format(self.from_date, self.to_date), **({"cost_center": cc} if cc else {})})
		pi.insert(ignore_permissions=True)
		pi.submit()
		self.db_set("purchase_invoice", pi.name)
		return pi.name

	@frappe.whitelist()
	def refresh_status(self):
		if self.status == "Approved" and self.purchase_invoice:
			out = frappe.db.get_value("Purchase Invoice", self.purchase_invoice, ["docstatus", "outstanding_amount"], as_dict=1)
			if out and out.docstatus == 1 and flt(out.outstanding_amount) <= 0.005:
				self.db_set("status", "Paid")
		return self.status

	@frappe.whitelist()
	def cancel_statement(self):
		frappe.has_permission("Doctor Statement", "write", self, throw=True)
		if self.status == "Cancelled":
			return self.status
		if self.status == "Paid":
			frappe.throw(_("The statement is paid. Cancel the payment first."))
		if self.purchase_invoice and frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "docstatus") == 1:
			pi = frappe.get_doc("Purchase Invoice", self.purchase_invoice)
			pi.cancel()
		frappe.db.sql("UPDATE `tabBill Line` SET statement = NULL WHERE statement = %s", self.name)
		self.db_set("status", "Cancelled")
		return self.status

	def on_trash(self):
		if self.status != "Draft":
			frappe.throw(_("Only a draft statement can be deleted. Cancel it instead."))
