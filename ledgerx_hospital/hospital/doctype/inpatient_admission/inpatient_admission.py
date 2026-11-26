import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, now_datetime

from ledgerx_hospital import billing, charges, data
from ledgerx_hospital.engine import beds
from ledgerx_hospital.engine.money import cents, money


def bed_row(bed):
	return frappe.db.get_value("Hospital Bed", bed, ["name", "bed_no", "status", "active", "branch", "ward", "charge_service", "current_admission"], as_dict=1)


def segments(adm):
	out = []
	for s in sorted(adm.stays, key=lambda x: get_datetime(x.from_time)):
		out.append({"bed": s.bed, "from": get_datetime(s.from_time), "to": get_datetime(s.to_time) if s.to_time else None, "rate": flt(s.daily_rate)})
	return out


class InpatientAdmission(Document):
	def validate(self):
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "status", "insurance_plan"], as_dict=1)
		self.patient_name = p.patient_name
		if self.is_new():
			if p.status == "Deceased":
				frappe.throw(_("The patient is marked deceased"))
			open_adm = frappe.db.get_value("Inpatient Admission", {"patient": self.patient, "status": "Admitted"}, "name")
			if open_adm:
				frappe.throw(_("The patient is already admitted: {0}").format(open_adm))
			b = bed_row(self.bed)
			if not b.active or b.status != "Available":
				frappe.throw(_("Bed {0} is not available ({1})").format(b.bed_no, _(b.status)))
			if b.branch != self.branch:
				frappe.throw(_("Bed {0} belongs to another branch").format(b.bed_no))
			if cint(data.settings().require_deposit) and not self.deposits:
				frappe.throw(_("A deposit is required before admission"))
			self.ward = b.ward
			self.insurance_plan = self.insurance_plan or p.insurance_plan
			rate = data.service_price(b.charge_service, self.insurance_plan or None, self.branch, self.admitted_on)
			self.set("stays", [{"bed": self.bed, "from_time": self.admitted_on, "daily_rate": rate}])
		if self.insurance_plan:
			data.check_plan_usable(self.insurance_plan, self.admitted_on)
		self.deposit_total = money(sum(cents(d.amount) for d in self.deposits))
		if self.status == "Discharged" and not self.discharge_type:
			frappe.throw(_("Choose the discharge type"))

	def after_insert(self):
		frappe.db.set_value("Hospital Bed", self.bed, {"status": "Occupied", "current_admission": self.name}, update_modified=False)
		if self.emergency_visit:
			frappe.db.set_value("Emergency Visit", self.emergency_visit, {"status": "Admitted", "admission": self.name, "disposition_time": now_datetime()}, update_modified=False)
		self.post_bed_days()

	def on_trash(self):
		if self.status != "Cancelled" and frappe.db.exists("Hospital Charge", {"admission": self.name, "status": ["!=", "Cancelled"]}):
			frappe.throw(_("The admission has charges. Cancel the admission instead of deleting it."))

	# ---------------------------------------------------------------- bed days
	def post_bed_days(self, until=None):
		"""Posts a charge for every bed day reached so far that was not posted yet. Posted days never change: a later transfer only affects later days."""
		if not cint(data.settings().post_bed_charges):
			return 0
		s = data.settings()
		until = get_datetime(until) if until else (get_datetime(self.discharged_on) if self.discharged_on else now_datetime())
		admit = get_datetime(self.admitted_on)
		days = beds.charge_days(segments(self), admit, until, cint(s.bed_cutoff_hour) if s.bed_cutoff_hour not in (None, "") else 12, cint(s.bed_min_days) if s.bed_min_days not in (None, "") else 1)
		made = 0
		for d in days:
			if d["n"] <= cint(self.charged_days):
				continue
			svc = frappe.db.get_value("Hospital Bed", d["bed"], "charge_service")
			charges.add_charge(self.patient, self.branch, service=svc, qty=1, rate=d["rate"], description=_("Bed day {0} ({1})").format(d["n"], d["date"]), doctor=None,
				source_doctype="Admission Bed Day", source_name="%s/%s" % (self.name, d["n"]), admission=self.name, insurance_plan=self.insurance_plan, posting_date=d["date"])
			made += 1
		if days:
			self.db_set("charged_days", len(days), update_modified=False)
		return made

	# ---------------------------------------------------------------- actions
	@frappe.whitelist(methods=["POST"])
	def transfer(self, bed):
		self.check_permission("write")
		frappe.has_permission("Inpatient Admission", "write", self, throw=True)
		if self.status != "Admitted":
			frappe.throw(_("The patient is not admitted"))
		if bed == self.bed:
			frappe.throw(_("The patient is already in this bed"))
		b = bed_row(bed)
		if not b.active or b.status != "Available" or b.branch != self.branch:
			frappe.throw(_("Bed {0} is not available in this branch").format(b.bed_no))
		now = now_datetime()
		self.post_bed_days(now)
		rate = data.service_price(b.charge_service, self.insurance_plan or None, self.branch, now)
		last = self.stays[-1]
		last.to_time = now
		self.append("stays", {"bed": bed, "from_time": now, "daily_rate": rate})
		old = self.bed
		self.bed, self.ward = bed, b.ward
		self.save()
		frappe.db.set_value("Hospital Bed", old, {"status": "Cleaning", "current_admission": None}, update_modified=False)
		frappe.db.set_value("Hospital Bed", bed, {"status": "Occupied", "current_admission": self.name}, update_modified=False)
		return bed

	@frappe.whitelist(methods=["POST"])
	def add_deposit(self, amount, mode_of_payment, reference_no=None):
		self.check_permission("write")
		frappe.has_permission("Inpatient Admission", "write", self, throw=True)
		if self.status != "Admitted":
			frappe.throw(_("The patient is not admitted"))
		pe = billing.receive_deposit(self.patient, self.branch, amount, mode_of_payment, self.name, reference_no)
		self.append("deposits", {"posting_date": frappe.utils.nowdate(), "amount": flt(amount), "mode_of_payment": mode_of_payment, "payment_entry": pe})
		self.save()
		return pe

	@frappe.whitelist(methods=["POST"])
	def discharge(self, discharge_type, summary=None):
		self.check_permission("write")
		frappe.has_permission("Inpatient Admission", "write", self, throw=True)
		if self.status != "Admitted":
			frappe.throw(_("The patient is not admitted"))
		if not discharge_type:
			frappe.throw(_("Choose the discharge type"))
		pending = frappe.db.count("Medication Administration", {"admission": self.name, "status": "Scheduled"})
		if pending:
			frappe.msgprint(_("{0} scheduled medicine doses are still open. They will be marked Missed.").format(pending), indicator="orange")
		now = now_datetime()
		self.post_bed_days(now)
		self.stays[-1].to_time = now
		self.status, self.discharged_on, self.discharge_type, self.discharge_summary = "Discharged", now, discharge_type, summary or self.discharge_summary
		self.save()
		frappe.db.sql("UPDATE `tabMedication Administration` SET status = 'Missed' WHERE admission = %s AND status = 'Scheduled'", self.name)
		frappe.db.set_value("Hospital Bed", self.bed, {"status": "Cleaning", "current_admission": None}, update_modified=False)
		if discharge_type == "Deceased":
			frappe.db.set_value("Hospital Patient", self.patient, {"status": "Deceased", "deceased_on": now}, update_modified=False)
		return self.status

	@frappe.whitelist(methods=["POST"])
	def cancel_admission(self):
		"""For an admission made by mistake: only when nothing was charged or ordered except the bed days."""
		self.check_permission("write")
		frappe.has_permission("Inpatient Admission", "write", self, throw=True)
		if self.status != "Admitted":
			frappe.throw(_("The patient is not admitted"))
		other = frappe.db.sql("""SELECT COUNT(*) FROM `tabHospital Charge` WHERE admission = %s AND status != 'Cancelled' AND source_doctype != 'Admission Bed Day'""", self.name)[0][0]
		if other:
			frappe.throw(_("The admission has other charges. Discharge the patient instead."))
		for c in frappe.get_all("Hospital Charge", filters={"admission": self.name, "status": ["!=", "Cancelled"]}, pluck="name"):
			charges.cancel_charge(c)
		self.status = "Cancelled"
		self.save()
		frappe.db.set_value("Hospital Bed", self.bed, {"status": "Available", "current_admission": None}, update_modified=False)
		return self.status
