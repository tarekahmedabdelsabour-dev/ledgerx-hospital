import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class InsuranceApproval(Document):
	def validate(self):
		if self.status in ("Approved", "Partially Approved"):
			if not self.approval_no:
				frappe.throw(_("Enter the insurer's approval number"))
			if not self.services:
				frappe.throw(_("List the approved services"))
		if self.valid_till and getdate(self.valid_till) < getdate() and self.status in ("Approved", "Partially Approved"):
			self.status = "Expired"
		plan = frappe.db.get_value("Hospital Insurance Plan", self.insurance_plan, "active")
		if not plan:
			frappe.throw(_("Insurance plan {0} is not active").format(self.insurance_plan))
