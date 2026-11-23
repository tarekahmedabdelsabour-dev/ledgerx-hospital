import frappe
from frappe import _
from frappe.utils import now_datetime


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"status": "Admitted"}
	if filters.branch:
		f["branch"] = filters.branch
	if filters.ward:
		f["ward"] = filters.ward
	rows = frappe.get_list("Inpatient Admission", filters=f, fields=["name", "patient", "patient_name", "ward", "bed", "admitted_on", "admitting_doctor", "insurance_plan", "branch"], order_by="ward, bed", limit_page_length=0)
	now = now_datetime()
	for r in rows:
		r["days"] = max((now - r.admitted_on).days, 0)
	cols = [
		{"label": _("Admission"), "fieldname": "name", "fieldtype": "Link", "options": "Inpatient Admission", "width": 130},
		{"label": _("Patient"), "fieldname": "patient", "fieldtype": "Link", "options": "Hospital Patient", "width": 110},
		{"label": _("Name"), "fieldname": "patient_name", "fieldtype": "Data", "width": 170},
		{"label": _("Ward"), "fieldname": "ward", "fieldtype": "Link", "options": "Ward", "width": 120},
		{"label": _("Bed"), "fieldname": "bed", "fieldtype": "Link", "options": "Hospital Bed", "width": 110},
		{"label": _("Admitted"), "fieldname": "admitted_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 60},
		{"label": _("Doctor"), "fieldname": "admitting_doctor", "fieldtype": "Link", "options": "Hospital Doctor", "width": 130},
		{"label": _("Insurance Plan"), "fieldname": "insurance_plan", "fieldtype": "Link", "options": "Hospital Insurance Plan", "width": 130},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Hospital Branch", "width": 120},
	]
	return cols, rows, None, None, [{"label": _("Patients in hospital"), "value": len(rows), "datatype": "Int"}]
