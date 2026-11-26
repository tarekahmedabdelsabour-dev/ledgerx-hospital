import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, now_datetime

from ledgerx_hospital import charges
from ledgerx_hospital.engine import triage

CLOSED = ("Admitted", "Discharged", "Transferred", "Deceased", "Left Without Being Seen")


class EmergencyVisit(Document):
	def validate(self):
		if not self.patient:
			if not cint(self.unidentified) or not self.temp_name:
				frappe.throw(_("Choose the patient, or tick Unidentified and enter a temporary name"))
		else:
			p = frappe.db.get_value("Hospital Patient", self.patient, ["insurance_plan", "status"], as_dict=1)
			if p.status == "Deceased" and self.is_new():
				frappe.throw(_("The patient is marked deceased"))
			self.insurance_plan = self.insurance_plan or p.insurance_plan
		if self.triage_level:
			self.triage_color = triage.COLORS[int(self.triage_level)]
			self.triaged_by = self.triaged_by or frappe.session.user
		else:
			self.triage_color = None
		if self.seen_at:
			self.wait_minutes = triage.wait_minutes(get_datetime(self.arrival_time), now_datetime(), get_datetime(self.seen_at))
		if self.status in ("In Treatment", "Observation") and not self.assigned_doctor:
			frappe.throw(_("Assign a doctor first"))

	def after_insert(self):
		self.add_fee()

	def add_fee(self):
		if self.patient and self.service and not self.charge:
			c = charges.add_charge(self.patient, self.branch, service=self.service, doctor=self.assigned_doctor, source_doctype="Emergency Visit", source_name=self.name,
				insurance_plan=self.insurance_plan, posting_date=str(self.arrival_time)[:10])
			self.db_set("charge", c)

	def check_open(self):
		if self.status in CLOSED:
			frappe.throw(_("The visit is closed ({0})").format(_(self.status)))

	@frappe.whitelist(methods=["POST"])
	def set_triage(self, level, vitals=None):
		self.check_permission("write")
		frappe.has_permission("Emergency Visit", "write", self, throw=True)
		self.check_open()
		if str(level) not in ("1", "2", "3", "4", "5"):
			frappe.throw(_("The triage level is 1 to 5"))
		self.triage_level = str(level)
		if vitals:
			self.vitals = vitals
		self.save()
		return self.triage_color

	@frappe.whitelist(methods=["POST"])
	def assign_doctor(self, doctor):
		self.check_permission("write")
		frappe.has_permission("Emergency Visit", "write", self, throw=True)
		self.check_open()
		if not frappe.db.get_value("Hospital Doctor", doctor, "active"):
			frappe.throw(_("The doctor is not active"))
		self.assigned_doctor = doctor
		if not self.seen_at:
			self.seen_at = now_datetime()
		if self.status == "Waiting":
			self.status = "In Treatment"
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def link_patient(self, patient):
		"""Attaches the registered patient to an unidentified visit and posts the visit fee."""
		self.check_permission("write")
		frappe.has_permission("Emergency Visit", "write", self, throw=True)
		if self.patient:
			frappe.throw(_("The visit already has a patient"))
		self.patient, self.unidentified = patient, 0
		self.save()
		self.add_fee()
		return self.patient

	@frappe.whitelist(methods=["POST"])
	def dispose(self, status, note=None):
		self.check_permission("write")
		frappe.has_permission("Emergency Visit", "write", self, throw=True)
		self.check_open()
		if status not in ("Observation", "Discharged", "Transferred", "Deceased", "Left Without Being Seen"):
			frappe.throw(_("Use Admit to admit the patient to a bed"))
		if status in ("Discharged", "Transferred", "Deceased") and not self.assigned_doctor:
			frappe.throw(_("Assign the treating doctor first"))
		self.status = status
		if note:
			self.notes = ((self.notes or "") + "\n" + note).strip()
		if status != "Observation":
			self.disposition_time = now_datetime()
		self.save()
		if status == "Deceased" and self.patient:
			frappe.db.set_value("Hospital Patient", self.patient, {"status": "Deceased", "deceased_on": now_datetime()}, update_modified=False)
		return self.status

	@frappe.whitelist(methods=["POST"])
	def admit(self, bed, doctor=None):
		self.check_permission("write")
		frappe.has_permission("Inpatient Admission", "create", throw=True)
		self.check_open()
		if not self.patient:
			frappe.throw(_("Register the patient and link them to this visit before admitting"))
		adm = frappe.get_doc({"doctype": "Inpatient Admission", "patient": self.patient, "branch": self.branch, "admitting_doctor": doctor or self.assigned_doctor, "admission_type": "Emergency",
			"admitted_on": now_datetime(), "bed": bed, "emergency_visit": self.name, "diagnosis": self.complaint, "insurance_plan": self.insurance_plan})
		if not adm.admitting_doctor:
			frappe.throw(_("Choose the admitting doctor"))
		adm.insert()
		return adm.name
