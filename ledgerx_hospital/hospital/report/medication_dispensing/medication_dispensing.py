import frappe
from frappe import _
from frappe.utils import add_days, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond, vals = ["d.docstatus = 1", "d.posting_date BETWEEN %(frm)s AND %(to)s"], {"frm": filters.from_date or add_days(nowdate(), -30), "to": filters.to_date or nowdate()}
	if filters.branch:
		cond.append("d.branch = %(branch)s")
		vals["branch"] = filters.branch
	rows = frappe.db.sql("""SELECT l.item_code, l.item_name, SUM(IF(d.is_return = 1, -l.qty, l.qty)) AS qty, SUM(IF(d.is_return = 1, -l.amount, l.amount)) AS amount,
		COUNT(DISTINCT d.patient) AS patients FROM `tabDispense Line` l INNER JOIN `tabMedication Dispense` d ON d.name = l.parent WHERE {w}
		GROUP BY l.item_code, l.item_name ORDER BY amount DESC""".format(w=" AND ".join(cond)), vals, as_dict=1)
	cols = [{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130}, {"label": _("Medicine"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Net Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 110}, {"label": _("Net Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Patients"), "fieldname": "patients", "fieldtype": "Int", "width": 90}]
	return cols, rows
