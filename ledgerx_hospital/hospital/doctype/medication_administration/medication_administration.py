import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class MedicationAdministration(Document):
	def validate(self):
		a = frappe.db.get_value("Inpatient Admission", self.admission, ["patient", "branch", "status"], as_dict=1)
		if self.is_new() and a.status != "Admitted":
			frappe.throw(_("The patient is not admitted"))
		self.patient, self.branch = a.patient, a.branch
		info = frappe.db.get_value("Item", self.item_code, ["is_stock_item", "disabled"], as_dict=1)
		if info.disabled:
			frappe.throw(_("Item {0} is disabled").format(self.item_code))
		if self.status == "Given" and not self.given_at:
			self.given_at, self.given_by = now_datetime(), frappe.session.user

	def _set(self, status, note=None):
		frappe.has_permission("Medication Administration", "write", self, throw=True)
		if self.status != "Scheduled":
			frappe.throw(_("This dose was already recorded as {0}").format(_(self.status)))
		self.status = status
		if status == "Given":
			self.given_at, self.given_by = now_datetime(), frappe.session.user
		if note:
			self.notes = ((self.notes or "") + "\n" + note).strip()
		self.save()
		return self.status

	@frappe.whitelist()
	def give(self, notes=None):
		return self._set("Given", notes)

	@frappe.whitelist()
	def hold(self, reason):
		if not reason:
			frappe.throw(_("Enter the reason"))
		return self._set("Held", reason)

	@frappe.whitelist()
	def refuse(self, reason=None):
		return self._set("Refused", reason)
