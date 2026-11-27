import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ledgerx_hospital import charges


class HospitalCharge(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("The quantity must be more than zero"))
		if flt(self.rate) < 0:
			frappe.throw(_("The rate cannot be negative"))
		if not 0 <= flt(self.discount_pct) <= 100:
			frappe.throw(_("The discount must be between 0 and 100"))
		if not self.is_new() and self.status == "Billed" and any(self.has_value_changed(f) for f in ("rate", "qty", "discount_pct", "service", "item_code", "patient")):
			frappe.throw(_("A billed charge cannot be edited. Cancel the bill first."))
		self._guard_price()
		self.amount = charges.net(self.qty, self.rate, self.discount_pct)

	def _guard_price(self):
		"""Only a manager sets a price or a discount by hand. Others get the list price and no discount."""
		if self.flags.system_charge or frappe.flags.in_install or frappe.flags.in_patch or frappe.session.user == "Administrator":
			return
		if set(frappe.get_roles()) & {"Hospital Manager", "System Manager"}:
			return
		if not self.is_new():
			if self.has_value_changed("rate") or self.has_value_changed("discount_pct"):
				frappe.throw(_("Only a manager can change the rate or the discount of a charge."), frappe.PermissionError)
			return
		if self.service:
			from ledgerx_hospital import data

			self.rate = flt(data.service_price(self.service, self.insurance_plan, self.branch, self.posting_date))
		self.discount_pct = 0

	def on_trash(self):
		if self.status == "Billed":
			frappe.throw(_("A billed charge cannot be deleted"))
