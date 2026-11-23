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
		if not self.is_new() and self.status == "Billed" and self.has_value_changed("rate"):
			frappe.throw(_("A billed charge cannot be edited. Cancel the bill first."))
		self.amount = charges.net(self.qty, self.rate, self.discount_pct)

	def on_trash(self):
		if self.status == "Billed":
			frappe.throw(_("A billed charge cannot be deleted"))
