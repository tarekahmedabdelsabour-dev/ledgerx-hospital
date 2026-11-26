import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from ledgerx_hospital import billing, data


class HospitalBill(Document):
	def validate(self):
		self.posting_date = self.posting_date or nowdate()
		self.company = data.company_of(self.branch)
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "status", "insurance_plan", "member_no"], as_dict=1)
		if p.status == "Deceased" and self.is_new():
			frappe.msgprint(_("The patient is marked deceased."), indicator="orange")
		if self.insurance_plan and not self.member_no:
			self.member_no = p.member_no
		if not self.lines:
			frappe.throw(_("The bill has no lines. Use Get Unbilled Charges."))
		billing.compute(self)
		if flt(self.patient_total) < 0 or flt(self.insurer_total) < 0:
			frappe.throw(_("The bill has a negative total"))
		if self.docstatus == 0:
			self.status = "Draft"

	@frappe.whitelist(methods=["POST"])
	def load_charges(self):
		"""Fills the bill with every unbilled charge of the patient (of this admission when one is chosen)."""
		self.check_permission("write")
		self.set("lines", [])
		for c in billing.unbilled(self.patient, self.admission or None, self.branch):
			self.append("lines", {"charge": c.name})
		if not self.lines:
			frappe.throw(_("The patient has no unbilled charges"))
		if self.insurance_plan:
			data.check_plan_usable(self.insurance_plan, self.posting_date)
		billing.compute(self)
		return self.as_dict()

	def on_submit(self):
		billing.post(self)

	def before_cancel(self):
		for fld in ("patient_invoice", "insurer_invoice"):
			inv = self.get(fld)
			if inv and billing.invoice_paid(inv) > 0:
				frappe.throw(_("Payments were received against invoice {0}. Cancel those payments first.").format(inv))

	def on_cancel(self):
		billing.unpost(self)
		billing.refresh(self.name)

	@frappe.whitelist(methods=["POST"])
	def receive_payment(self, amount, mode_of_payment, reference_no=None):
		self.check_permission("write")
		frappe.has_permission("Hospital Bill", "write", self, throw=True)
		return billing.receive_payment(self.name, amount, mode_of_payment, reference_no)
