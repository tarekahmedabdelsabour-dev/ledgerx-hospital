import frappe
from frappe import _
from frappe.utils import add_days, nowdate

from ledgerx_hospital import billing, data


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond, vals = ["b.docstatus = 1", "bl.doctor IS NOT NULL", "bl.doctor != ''", "IFNULL(bl.statement, '') = ''", "bl.doctor_share != 0", "b.posting_date BETWEEN %(frm)s AND %(to)s"], \
		{"frm": filters.from_date or add_days(nowdate(), -30), "to": filters.to_date or nowdate()}
	if filters.branch:
		cond.append("b.branch = %(branch)s")
		vals["branch"] = filters.branch
	if filters.doctor:
		cond.append("bl.doctor = %(doctor)s")
		vals["doctor"] = filters.doctor
	lines = frappe.db.sql("""SELECT bl.doctor, b.name AS bill, bl.amount, bl.doctor_share FROM `tabBill Line` bl INNER JOIN `tabHospital Bill` b ON b.name = bl.parent WHERE {w}""".format(w=" AND ".join(cond)), vals, as_dict=1)
	paid_basis = data.settings().commission_basis == "Paid"
	cache, groups = {}, {}
	for l in lines:
		ready = True
		if paid_basis:
			if l.bill not in cache:
				cache[l.bill] = billing.is_fully_paid(l.bill)
			ready = cache[l.bill]
		g = groups.setdefault(l.doctor, {"doctor": l.doctor, "lines": 0, "amount": 0, "share": 0, "waiting": 0})
		if ready:
			g["lines"] += 1
			g["amount"] += l.amount or 0
			g["share"] += l.doctor_share or 0
		else:
			g["waiting"] += l.doctor_share or 0
	names = {d.name: d.doctor_name for d in frappe.get_all("Hospital Doctor", fields=["name", "doctor_name"])}
	rows = sorted(({**g, "doctor_name": names.get(g["doctor"])} for g in groups.values()), key=lambda r: -r["share"])
	cols = [{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Hospital Doctor", "width": 120}, {"label": _("Name"), "fieldname": "doctor_name", "fieldtype": "Data", "width": 180},
		{"label": _("Lines"), "fieldname": "lines", "fieldtype": "Int", "width": 70}, {"label": _("Billed Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Doctor's Share Due"), "fieldname": "share", "fieldtype": "Currency", "width": 140}, {"label": _("Waiting for Payment"), "fieldname": "waiting", "fieldtype": "Currency", "width": 140}]
	return cols, rows, None, None, [{"label": _("Total due"), "value": sum(r["share"] for r in rows), "datatype": "Currency"}]
