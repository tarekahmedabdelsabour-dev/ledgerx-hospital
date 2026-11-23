import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime

from ledgerx_hospital import data
from ledgerx_hospital.engine import people


class HospitalPatient(Document):
	def validate(self):
		self.patient_name = (self.patient_name or "").strip()
		self.national_id = str(self.national_id or "").translate(people.AR).strip() or None
		if self.national_id:
			info = people.parse_national_id(self.national_id)
			if not info["valid"]:
				frappe.throw(_("The national ID is not valid. It must be 14 digits and start with 2 or 3."))
			dup = frappe.db.get_value("Hospital Patient", {"national_id": self.national_id, "name": ["!=", self.name or ""]}, "name")
			if dup:
				frappe.throw(_("National ID {0} already belongs to patient {1}").format(self.national_id, dup))
			if not self.date_of_birth:
				self.date_of_birth = info["birth_date"]
			elif getdate(self.date_of_birth) != info["birth_date"]:
				frappe.msgprint(_("The date of birth does not match the national ID."), indicator="orange")
			if not self.gender:
				self.gender = info["gender"]
		elif cint(data.settings().require_national_id) and not self.passport_no:
			frappe.throw(_("Enter the national ID (or the passport number for a foreigner)"))
		if self.date_of_birth:
			if getdate(self.date_of_birth) > getdate():
				frappe.throw(_("The date of birth is in the future"))
			self.age = people.age_text(getdate(self.date_of_birth), lang="ar" if frappe.local.lang == "ar" else "en")
		if self.status == "Deceased" and not self.deceased_on:
			self.deceased_on = now_datetime()
		if self.status != "Deceased":
			self.deceased_on = None
		if self.insurance_expiry and self.insurance_plan and getdate(self.insurance_expiry) < getdate():
			frappe.msgprint(_("The insurance card has expired."), indicator="orange")

	def after_insert(self):
		data.patient_customer(self.name)

	def on_update(self):
		if self.customer and self.has_value_changed("patient_name"):
			frappe.db.set_value("Customer", self.customer, "customer_name", self.patient_name, update_modified=False)

	def on_trash(self):
		for dt in ("Hospital Charge", "Hospital Bill", "Patient Encounter", "Inpatient Admission"):
			if frappe.db.exists(dt, {"patient": self.name}):
				frappe.throw(_("The patient has records in {0}. Mark the patient Inactive instead of deleting."). format(_(dt)))
