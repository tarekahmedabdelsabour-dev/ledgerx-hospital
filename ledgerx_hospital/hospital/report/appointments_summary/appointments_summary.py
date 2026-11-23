import frappe
from frappe import _
from frappe.utils import add_days, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond, vals = ["appointment_date BETWEEN %(frm)s AND %(to)s"], {"frm": filters.from_date or add_days(nowdate(), -30), "to": filters.to_date or nowdate()}
	if filters.branch:
		cond.append("branch = %(branch)s")
		vals["branch"] = filters.branch
	if filters.doctor:
		cond.append("doctor = %(doctor)s")
		vals["doctor"] = filters.doctor
	rows = frappe.db.sql("""SELECT doctor, doctor_name, COUNT(*) AS total, SUM(status = 'Completed') AS completed, SUM(status = 'No Show') AS no_show, SUM(status = 'Cancelled') AS cancelled,
		SUM(status = 'Scheduled') AS scheduled, SUM(is_follow_up = 1) AS follow_ups FROM `tabPatient Appointment` WHERE {w} GROUP BY doctor, doctor_name ORDER BY total DESC""".format(w=" AND ".join(cond)), vals, as_dict=1)
	for r in rows:
		due = (r.total or 0) - (r.cancelled or 0) - (r.scheduled or 0)
		r["no_show_pct"] = round((r.no_show or 0) * 100.0 / due, 1) if due else 0
	cols = [{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Hospital Doctor", "width": 120}, {"label": _("Name"), "fieldname": "doctor_name", "fieldtype": "Data", "width": 170},
		{"label": _("Appointments"), "fieldname": "total", "fieldtype": "Int", "width": 100}, {"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 90},
		{"label": _("No Show"), "fieldname": "no_show", "fieldtype": "Int", "width": 80}, {"label": _("Cancelled"), "fieldname": "cancelled", "fieldtype": "Int", "width": 90},
		{"label": _("Still Scheduled"), "fieldname": "scheduled", "fieldtype": "Int", "width": 110}, {"label": _("Follow-ups"), "fieldname": "follow_ups", "fieldtype": "Int", "width": 90},
		{"label": _("No Show %"), "fieldname": "no_show_pct", "fieldtype": "Percent", "width": 90}]
	return cols, rows
