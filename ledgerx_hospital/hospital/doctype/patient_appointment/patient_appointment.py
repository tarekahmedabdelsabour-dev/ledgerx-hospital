import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate, now_datetime

from ledgerx_hospital import charges, data
from ledgerx_hospital.engine import slots

LIVE = ("Scheduled", "Checked In", "In Consultation", "Completed")


def doctor_rows(doctor):
	d = frappe.get_cached_doc("Hospital Doctor", doctor)
	sched = [{"weekday": r.weekday, "branch": r.branch, "from_time": r.from_time, "to_time": r.to_time, "slot_minutes": r.slot_minutes, "capacity": r.capacity} for r in d.schedule]
	offs = [{"from_date": getdate(t.from_date), "to_date": getdate(t.to_date or t.from_date)} for t in d.time_off]
	return d, sched, offs


def booked_on(doctor, day, exclude=None):
	rows = frappe.get_all("Patient Appointment", filters={"doctor": doctor, "appointment_date": day, "status": ["in", list(LIVE)], "name": ["!=", exclude or ""]}, fields=["from_time", "to_time"])
	return [{"start": r.from_time, "end": r.to_time} for r in rows]


class PatientAppointment(Document):
	def validate(self):
		d, sched, offs = doctor_rows(self.doctor)
		if not d.active:
			frappe.throw(_("Doctor {0} is not active").format(d.doctor_name))
		self.doctor_name = d.doctor_name
		self.patient_name = frappe.db.get_value("Hospital Patient", self.patient, "patient_name")
		if not self.insurance_plan:
			self.insurance_plan = frappe.db.get_value("Hospital Patient", self.patient, "insurance_plan")
		if self.insurance_plan:
			data.check_plan_usable(self.insurance_plan, self.appointment_date)
		step = cint(data.settings().appointment_minutes) or 15
		start = slots.to_minutes(self.from_time)
		if start is None:
			frappe.throw(_("Choose the appointment time"))
		day = getdate(self.appointment_date)
		avail = slots.day_slots(day, sched, offs, booked_on(self.doctor, self.appointment_date, self.name), self.branch, None)
		slot = next((x for x in avail if x["start"] == start), None)
		if slot:
			self.to_time = slots.hhmm(slot["end"]) + ":00"
		elif not self.to_time:
			self.to_time = slots.hhmm(start + step) + ":00"
		if slots.to_minutes(self.to_time) <= start:
			frappe.throw(_("The end time must be after the start time"))
		if self.status in LIVE and self.is_new() and day < getdate(nowdate()):
			frappe.throw(_("The date is in the past"))
		if self.status == "Scheduled" and not cint(data.settings().allow_overbooking):
			if not slot:
				frappe.throw(_("This time is not one of the doctor's slots (outside the schedule or on leave)."))
			if not slot["free"]:
				frappe.throw(_("This slot is already fully booked."))
		clash = frappe.db.exists("Patient Appointment", {"patient": self.patient, "appointment_date": self.appointment_date, "from_time": self.from_time, "status": ["in", list(LIVE)], "name": ["!=", self.name or ""]})
		if clash:
			frappe.throw(_("The patient already has an appointment at this time: {0}").format(clash))
		last = frappe.db.get_value("Patient Appointment", {"patient": self.patient, "doctor": self.doctor, "status": "Completed", "name": ["!=", self.name or ""]}, "appointment_date", order_by="appointment_date desc")
		window = cint(d.followup_days) or cint(data.settings().followup_days)
		self.is_follow_up = 1 if (last and window and slots.is_follow_up(getdate(last), getdate(self.appointment_date), window)) else 0
		if self.is_follow_up and self.appointment_type == "Consultation":
			self.appointment_type = "Follow-up"
		if self.status == "Cancelled" and not self.cancel_reason:
			frappe.throw(_("Enter the reason for cancelling"))

	@frappe.whitelist(methods=["POST"])
	def check_in(self):
		self.check_permission("write")
		frappe.has_permission("Patient Appointment", "write", self, throw=True)
		if self.status != "Scheduled":
			frappe.throw(_("Only a scheduled appointment can be checked in"))
		if getdate(self.appointment_date) != getdate(nowdate()):
			frappe.throw(_("The appointment is not today"))
		nos = [r[0] for r in frappe.db.sql("SELECT queue_no FROM `tabPatient Appointment` WHERE doctor = %s AND appointment_date = %s AND branch = %s FOR UPDATE", (self.doctor, self.appointment_date, self.branch))]
		self.queue_no = slots.next_queue_no([n for n in nos if n])
		self.status, self.checked_in_at = "Checked In", now_datetime()
		self.charge = self.add_fee()
		self.save()
		return {"queue_no": self.queue_no, "charge": self.charge}

	def add_fee(self):
		d = frappe.get_cached_doc("Hospital Doctor", self.doctor)
		service = self.service or d.consultation_service
		if not service:
			return None
		factor = 1.0
		if cint(self.is_follow_up) and flt(data.settings().followup_fee_pct):
			factor = flt(data.settings().followup_fee_pct) / 100.0
		return charges.add_charge(self.patient, self.branch, service=service, doctor=self.doctor, source_doctype="Patient Appointment", source_name=self.name,
			insurance_plan=self.insurance_plan, posting_date=self.appointment_date, rate_factor=factor)

	@frappe.whitelist(methods=["POST"])
	def cancel_appointment(self, reason):
		self.check_permission("write")
		frappe.has_permission("Patient Appointment", "write", self, throw=True)
		if self.status in ("In Consultation", "Completed"):
			frappe.throw(_("A consultation that started cannot be cancelled"))
		if not reason:
			frappe.throw(_("Enter the reason for cancelling"))
		if self.charge:
			charges.cancel_charge(self.charge)
			self.charge = None
		self.status, self.cancel_reason = "Cancelled", reason
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def start_encounter(self):
		"""Opens the doctor's visit record for a checked-in patient."""
		self.check_permission("write")
		frappe.has_permission("Patient Encounter", "create", throw=True)
		if self.status not in ("Checked In", "In Consultation"):
			frappe.throw(_("Check the patient in first"))
		if self.encounter:
			return self.encounter
		enc = frappe.get_doc({"doctype": "Patient Encounter", "patient": self.patient, "doctor": self.doctor, "branch": self.branch, "encounter_date": now_datetime(),
			"encounter_type": "Outpatient", "appointment": self.name, "insurance_plan": self.insurance_plan, "chief_complaint": self.reason})
		enc.insert()
		self.db_set({"encounter": enc.name, "status": "In Consultation"})
		return enc.name


@frappe.whitelist()
def free_slots(doctor, date, branch=None, exclude=None):
	frappe.has_permission("Patient Appointment", "read", throw=True)
	d, sched, offs = doctor_rows(doctor)
	out = slots.day_slots(getdate(date), sched, offs, booked_on(doctor, date, exclude), branch, now_datetime())
	return [s for s in out if s.get("free")]
