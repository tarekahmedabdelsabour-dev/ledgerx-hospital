"""Whitelisted endpoints for the desk screens. Every one reads through frappe.get_list, so roles and branch restrictions apply."""
import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime

from ledgerx_hospital.engine import triage


def _need(doctype):
	frappe.has_permission(doctype, "read", throw=True)


@frappe.whitelist()
def available_beds(branch, ward=None, bed_class=None):
	_need("Hospital Bed")
	f = {"branch": branch, "status": "Available", "active": 1}
	if ward:
		f["ward"] = ward
	if bed_class:
		f["bed_class"] = bed_class
	return frappe.get_list("Hospital Bed", filters=f, fields=["name", "bed_no", "ward", "room_no", "bed_class", "charge_service"], order_by="ward, bed_no", limit_page_length=500)


@frappe.whitelist()
def bed_board(branch):
	"""Every bed of a branch with the patient in it, grouped by ward, and the occupancy."""
	_need("Hospital Bed")
	beds = frappe.get_list("Hospital Bed", filters={"branch": branch, "active": 1}, fields=["name", "bed_no", "ward", "room_no", "bed_class", "status", "current_admission"],
		order_by="ward, bed_no", limit_page_length=2000)
	adm = {a.name: a for a in frappe.get_list("Inpatient Admission", filters={"branch": branch, "status": "Admitted"}, fields=["name", "patient", "patient_name", "admitted_on", "admitting_doctor"],
		limit_page_length=2000)}
	out = {}
	occupied = 0
	for b in beds:
		a = adm.get(b.current_admission)
		if b.status == "Occupied":
			occupied += 1
		out.setdefault(b.ward, []).append({**b, "patient": a.patient if a else None, "patient_name": a.patient_name if a else None, "admitted_on": a.admitted_on if a else None})
	usable = len([b for b in beds if b.status != "Maintenance"])
	from ledgerx_hospital.engine.beds import occupancy_pct

	return {"wards": out, "total": len(beds), "occupied": occupied, "occupancy_pct": occupancy_pct(occupied, usable)}


@frappe.whitelist()
def er_board(branch):
	"""The emergency queue: sickest first, longest waiting first, with who is overdue against the target."""
	_need("Emergency Visit")
	rows = frappe.get_list("Emergency Visit", filters={"branch": branch, "status": ["in", ["Waiting", "In Treatment", "Observation"]]},
		fields=["name", "patient", "temp_name", "complaint", "triage_level", "triage_color", "status", "arrival_time", "seen_at", "assigned_doctor"], limit_page_length=500)
	now = now_datetime()
	visits = [{"name": r.name, "level": cint(r.triage_level) or None, "arrival": get_datetime(r.arrival_time), "row": r} for r in rows]
	out = []
	for v in triage.queue_order(visits):
		r = v["row"]
		out.append({**r, "wait_minutes": triage.wait_minutes(v["arrival"], now, get_datetime(r.seen_at) if r.seen_at else None),
			"overdue": bool(v["level"]) and triage.is_overdue(v["level"], v["arrival"], now, get_datetime(r.seen_at) if r.seen_at else None)})
	return out


@frappe.whitelist()
def patient_summary(patient):
	"""What the front desk and the doctor want to see at a glance."""
	frappe.has_permission("Hospital Patient", "read", doc=patient, throw=True)
	p = frappe.db.get_value("Hospital Patient", patient, ["patient_name", "age", "gender", "blood_group", "allergies", "chronic_conditions", "insurance_plan", "insurance_expiry", "mobile", "status"], as_dict=1)
	unbilled = frappe.db.sql("""SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM `tabHospital Charge` WHERE patient = %s AND status = 'Unbilled'""", patient)[0]
	owed = frappe.db.sql("""SELECT COALESCE(SUM(patient_outstanding), 0) FROM `tabHospital Bill` WHERE patient = %s AND docstatus = 1""", patient)[0][0]
	adm = frappe.db.get_value("Inpatient Admission", {"patient": patient, "status": "Admitted"}, ["name", "bed", "ward", "admitted_on"], as_dict=1)
	enc = frappe.get_list("Patient Encounter", filters={"patient": patient}, fields=["name", "encounter_date", "doctor", "status"], order_by="encounter_date desc", limit_page_length=5)
	nxt = frappe.get_list("Patient Appointment", filters={"patient": patient, "status": "Scheduled", "appointment_date": [">=", frappe.utils.nowdate()]},
		fields=["name", "appointment_date", "from_time", "doctor_name"], order_by="appointment_date, from_time", limit_page_length=3)
	return {"patient": p, "unbilled_count": unbilled[0], "unbilled_total": flt(unbilled[1]), "patient_owes": flt(owed), "admission": adm, "recent_visits": enc, "next_appointments": nxt}


@frappe.whitelist()
def doctor_queue(doctor=None, branch=None):
	"""Today's appointments in queue order for one doctor (default: the doctor linked to the current user)."""
	_need("Patient Appointment")
	doctor = doctor or frappe.db.get_value("Hospital Doctor", {"user": frappe.session.user}, "name")
	if not doctor:
		return []
	f = {"doctor": doctor, "appointment_date": frappe.utils.nowdate(), "status": ["in", ["Scheduled", "Checked In", "In Consultation"]]}
	if branch:
		f["branch"] = branch
	return frappe.get_list("Patient Appointment", filters=f, fields=["name", "patient", "patient_name", "from_time", "status", "queue_no", "is_follow_up", "encounter"],
		order_by="status desc, queue_no asc, from_time asc", limit_page_length=300)


@frappe.whitelist()
def unbilled_charges(patient, admission=None):
	_need("Hospital Charge")
	f = {"patient": patient, "status": "Unbilled"}
	if admission:
		f["admission"] = admission
	return frappe.get_list("Hospital Charge", filters=f, fields=["name", "posting_date", "description", "service_type", "qty", "rate", "amount", "doctor"], order_by="posting_date, creation", limit_page_length=1000)


@frappe.whitelist()
def pending_work(branch=None):
	"""Counters for the front screen: what waits for someone to act."""
	out = {}
	for key, dt, flt_ in (
		("lab_to_collect", "Lab Order", {"status": "Ordered"}),
		("lab_in_progress", "Lab Order", {"status": "In Progress"}),
		("radiology_waiting", "Radiology Order", {"status": ["in", ["Ordered", "Scheduled"]]}),
		("er_waiting", "Emergency Visit", {"status": "Waiting"}),
		("approvals_waiting", "Insurance Approval", {"status": "Requested"}),
	):
		if not frappe.has_permission(dt, "read"):
			continue
		f = dict(flt_)
		if branch:
			f["branch"] = branch
		out[key] = frappe.get_list(dt, filters=f, fields=["count(name) as n"], limit_page_length=1)[0].n
	return out
