import frappe
from frappe import _
from frappe.utils import add_days, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	v = {"frm": filters.from_date or add_days(nowdate(), -30), "to": filters.to_date or nowdate()}

	def q(sql):
		return {r[0]: r[1] for r in frappe.db.sql(sql, v)}
	revenue = q("SELECT branch, SUM(amount) FROM `tabHospital Charge` WHERE status != 'Cancelled' AND posting_date BETWEEN %(frm)s AND %(to)s GROUP BY branch")
	appts = q("SELECT branch, COUNT(*) FROM `tabPatient Appointment` WHERE status IN ('Checked In', 'In Consultation', 'Completed') AND appointment_date BETWEEN %(frm)s AND %(to)s GROUP BY branch")
	adms = q("SELECT branch, COUNT(*) FROM `tabInpatient Admission` WHERE status != 'Cancelled' AND DATE(admitted_on) BETWEEN %(frm)s AND %(to)s GROUP BY branch")
	er = q("SELECT branch, COUNT(*) FROM `tabEmergency Visit` WHERE DATE(arrival_time) BETWEEN %(frm)s AND %(to)s GROUP BY branch")
	surg = q("SELECT branch, COUNT(*) FROM `tabSurgery Booking` WHERE status = 'Completed' AND DATE(scheduled_start) BETWEEN %(frm)s AND %(to)s GROUP BY branch")
	labs = q("SELECT branch, COUNT(*) FROM `tabLab Order` WHERE status != 'Cancelled' AND ordered_on BETWEEN %(frm)s AND CONCAT(%(to)s, ' 23:59:59') GROUP BY branch")
	rows = []
	for b in frappe.get_list("Hospital Branch", fields=["name"], limit_page_length=0):
		n = b.name
		rows.append({"branch": n, "revenue": revenue.get(n) or 0, "visits": appts.get(n) or 0, "admissions": adms.get(n) or 0, "emergency": er.get(n) or 0, "surgeries": surg.get(n) or 0, "lab_orders": labs.get(n) or 0})
	cols = [{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Hospital Branch", "width": 180}, {"label": _("Charges"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
		{"label": _("Clinic Visits"), "fieldname": "visits", "fieldtype": "Int", "width": 100}, {"label": _("Admissions"), "fieldname": "admissions", "fieldtype": "Int", "width": 100},
		{"label": _("Emergency Visits"), "fieldname": "emergency", "fieldtype": "Int", "width": 120}, {"label": _("Surgeries"), "fieldname": "surgeries", "fieldtype": "Int", "width": 90},
		{"label": _("Lab Orders"), "fieldname": "lab_orders", "fieldtype": "Int", "width": 90}]
	return cols, rows
