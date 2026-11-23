import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"status": "Unbilled"}
	if filters.branch:
		f["branch"] = filters.branch
	if filters.patient:
		f["patient"] = filters.patient
	rows = frappe.get_list("Hospital Charge", filters=f, fields=["name", "patient", "posting_date", "description", "service_type", "qty", "amount", "doctor", "admission", "branch"], order_by="posting_date asc", limit_page_length=0)
	today = getdate(nowdate())
	for r in rows:
		r["age"] = date_diff(today, r.posting_date)
	if filters.min_age:
		rows = [r for r in rows if r["age"] >= int(filters.min_age)]
	cols = [
		{"label": _("Charge"), "fieldname": "name", "fieldtype": "Link", "options": "Hospital Charge", "width": 130},
		{"label": _("Patient"), "fieldname": "patient", "fieldtype": "Link", "options": "Hospital Patient", "width": 110},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Age (days)"), "fieldname": "age", "fieldtype": "Int", "width": 90},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
		{"label": _("Type"), "fieldname": "service_type", "fieldtype": "Data", "width": 100},
		{"label": _("Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Admission"), "fieldname": "admission", "fieldtype": "Link", "options": "Inpatient Admission", "width": 130},
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Hospital Doctor", "width": 120},
	]
	return cols, rows, None, None, [{"label": _("Unbilled amount"), "value": sum(r.amount or 0 for r in rows), "datatype": "Currency"}]
