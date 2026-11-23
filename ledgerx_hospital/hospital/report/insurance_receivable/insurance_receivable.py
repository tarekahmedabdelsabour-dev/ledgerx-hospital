import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from ledgerx_hospital.engine import claims


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond, vals = ["b.docstatus = 1", "si.docstatus = 1", "si.outstanding_amount > 0.005"], {}
	if filters.insurance_company:
		cond.append("p.insurance_company = %(ic)s")
		vals["ic"] = filters.insurance_company
	if filters.branch:
		cond.append("b.branch = %(branch)s")
		vals["branch"] = filters.branch
	rows = frappe.db.sql("""SELECT p.insurance_company, b.name AS bill, b.patient, b.posting_date, b.claim, si.name AS invoice, si.due_date, si.grand_total, si.outstanding_amount AS outstanding
		FROM `tabHospital Bill` b INNER JOIN `tabHospital Insurance Plan` p ON p.name = b.insurance_plan INNER JOIN `tabSales Invoice` si ON si.name = b.insurer_invoice
		WHERE {w} ORDER BY p.insurance_company, si.due_date""".format(w=" AND ".join(cond)), vals, as_dict=1)
	today = getdate(nowdate())
	buckets = {}
	for r in rows:
		r["days"] = claims.days_overdue(getdate(r.due_date or r.posting_date), today)
		r["bucket"] = claims.aging_bucket(r["days"]) if r["days"] > 0 else _("Not due")
		buckets[r["bucket"]] = buckets.get(r["bucket"], 0) + (r.outstanding or 0)
	cols = [
		{"label": _("Insurer"), "fieldname": "insurance_company", "fieldtype": "Link", "options": "Hospital Insurer", "width": 150},
		{"label": _("Bill"), "fieldname": "bill", "fieldtype": "Link", "options": "Hospital Bill", "width": 130},
		{"label": _("Patient"), "fieldname": "patient", "fieldtype": "Link", "options": "Hospital Patient", "width": 110},
		{"label": _("Claim"), "fieldname": "claim", "fieldtype": "Link", "options": "Insurance Claim", "width": 130},
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
		{"label": _("Due"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Invoiced"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 110},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 110},
		{"label": _("Days Overdue"), "fieldname": "days", "fieldtype": "Int", "width": 100},
		{"label": _("Age Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 100},
	]
	summary = [{"label": _("Outstanding"), "value": sum(r.outstanding or 0 for r in rows), "datatype": "Currency"}]
	summary += [{"label": k, "value": v, "datatype": "Currency"} for k, v in sorted(buckets.items())]
	return cols, rows, None, None, summary
