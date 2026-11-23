import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class NursingNote(Document):
	def validate(self):
		a = frappe.db.get_value("Inpatient Admission", self.admission, ["patient", "branch", "status"], as_dict=1)
		if self.is_new() and a.status != "Admitted":
			frappe.throw(_("The patient is not admitted"))
		self.patient, self.branch = a.patient, a.branch
		self.author = self.author or frappe.session.user
		self.recorded_at = self.recorded_at or now_datetime()
