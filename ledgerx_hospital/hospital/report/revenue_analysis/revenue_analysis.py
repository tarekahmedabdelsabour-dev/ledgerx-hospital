import frappe
from frappe import _
from frappe.utils import add_days, nowdate

GROUPS = {"Service Type": ("service_type", None), "Department": ("department", "Hospital Department"), "Doctor": ("doctor", "Hospital Doctor"), "Service": ("service", "Hospital Service"),
	"Branch": ("branch", "Hospital Branch"), "Insurance Plan": ("insurance_plan", "Hospital Insurance Plan")}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	by = GROUPS.get(filters.group_by or "Service Type")
	col = by[0]
	cond, vals = ["status != 'Cancelled'", "posting_date BETWEEN %(frm)s AND %(to)s"], {"frm": filters.from_date or add_days(nowdate(), -30), "to": filters.to_date or nowdate()}
	if filters.branch:
		cond.append("branch = %(branch)s")
		vals["branch"] = filters.branch
	if filters.billed == "Billed":
		cond.append("status = 'Billed'")
	elif filters.billed == "Unbilled":
		cond.append("status = 'Unbilled'")
	rows = frappe.db.sql("""SELECT IFNULL(NULLIF({c}, ''), %(none)s) AS grp, COUNT(*) AS lines, SUM(qty) AS qty, SUM(amount) AS amount, COUNT(DISTINCT patient) AS patients
		FROM `tabHospital Charge` WHERE {w} GROUP BY IFNULL(NULLIF({c}, ''), %(none)s) ORDER BY amount DESC""".format(c=col, w=" AND ".join(cond)), {**vals, "none": _("Not set")}, as_dict=1)
	total = sum(r.amount or 0 for r in rows) or 0
	for r in rows:
		r["share"] = round((r.amount or 0) * 100.0 / total, 1) if total else 0
	cols = [{"label": _(filters.group_by or "Service Type"), "fieldname": "grp", "fieldtype": "Link" if by[1] else "Data", "options": by[1], "width": 220},
		{"label": _("Charges"), "fieldname": "lines", "fieldtype": "Int", "width": 90}, {"label": _("Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Patients"), "fieldname": "patients", "fieldtype": "Int", "width": 90}, {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Share %"), "fieldname": "share", "fieldtype": "Percent", "width": 90}]
	return cols, rows, None, None, [{"label": _("Total"), "value": total, "datatype": "Currency"}]
