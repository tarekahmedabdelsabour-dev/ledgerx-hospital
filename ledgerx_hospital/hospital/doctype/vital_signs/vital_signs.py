import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from ledgerx_hospital.engine import people, vitals


class VitalSigns(Document):
	def validate(self):
		self.recorded_at = self.recorded_at or now_datetime()
		self.recorded_by = self.recorded_by or frappe.session.user
		self.bmi = vitals.bmi(self.weight, self.height) or 0
		born = frappe.db.get_value("Hospital Patient", self.patient, "date_of_birth")
		adult = (people.age_years(getdate(born)) >= 18) if born else True
		self.bmi_band = vitals.bmi_band(self.bmi or None, adult)
		flags = vitals.out_of_range({k: self.get(k) for k in vitals.DEFAULT_LIMITS})
		self.range_flags = ", ".join("%s: %s" % (frappe.unscrub(k), v) for k, v in flags.items())
