import frappe
from frappe import _
from frappe.model.document import Document


class HospitalBed(Document):
	def validate(self):
		if self.ward and not self.branch:
			self.branch = frappe.db.get_value("Ward", self.ward, "branch")
		if self.status != "Occupied" and self.current_admission and self.flags.get("from_admission") is None:
			if frappe.db.get_value("Inpatient Admission", self.current_admission, "status") == "Admitted":
				frappe.throw(_("The bed holds an admitted patient. Discharge or transfer the patient first."))
		if self.status == "Occupied" and not self.current_admission:
			frappe.throw(_("A bed becomes Occupied by admitting a patient, not by hand."))
		if not self.active and self.current_admission:
			frappe.throw(_("The bed is in use and cannot be deactivated"))
