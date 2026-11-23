import frappe
from frappe import _
from frappe.utils import add_days, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond, vals = ["t.collected_on IS NOT NULL", "r.resulted_on IS NOT NULL", "DATE(t.collected_on) BETWEEN %(frm)s AND %(to)s"], {"frm": filters.from_date or add_days(nowdate(), -30), "to": filters.to_date or nowdate()}
	if filters.branch:
		cond.append("o.branch = %(branch)s")
		vals["branch"] = filters.branch
	rows = frappe.db.sql("""SELECT t.service, COUNT(*) AS tests, AVG(TIMESTAMPDIFF(MINUTE, t.collected_on, r.resulted_on)) AS avg_minutes,
		MAX(TIMESTAMPDIFF(MINUTE, t.collected_on, r.resulted_on)) AS max_minutes, MAX(IFNULL(tp.tat_hours, 0)) AS target_hours,
		SUM(tp.tat_hours > 0 AND TIMESTAMPDIFF(MINUTE, t.collected_on, r.resulted_on) > tp.tat_hours * 60) AS late
		FROM `tabLab Order Test` t INNER JOIN `tabLab Order` o ON o.name = t.parent INNER JOIN `tabLab Result` r ON r.name = t.result
		LEFT JOIN `tabLab Test Template` tp ON tp.name = t.service WHERE {w} GROUP BY t.service ORDER BY tests DESC""".format(w=" AND ".join(cond)), vals, as_dict=1)
	for r in rows:
		r["avg_minutes"] = round(r.avg_minutes or 0)
		r["late_pct"] = round((r.late or 0) * 100.0 / r.tests, 1) if r.target_hours else None
	cols = [{"label": _("Test"), "fieldname": "service", "fieldtype": "Link", "options": "Hospital Service", "width": 220}, {"label": _("Tests"), "fieldname": "tests", "fieldtype": "Int", "width": 80},
		{"label": _("Average (min)"), "fieldname": "avg_minutes", "fieldtype": "Int", "width": 110}, {"label": _("Longest (min)"), "fieldname": "max_minutes", "fieldtype": "Int", "width": 110},
		{"label": _("Target (hours)"), "fieldname": "target_hours", "fieldtype": "Int", "width": 110}, {"label": _("Late"), "fieldname": "late", "fieldtype": "Int", "width": 70},
		{"label": _("Late %"), "fieldname": "late_pct", "fieldtype": "Percent", "width": 80}]
	return cols, rows
