import frappe
from frappe import _

from ledgerx_hospital.engine.beds import occupancy_pct


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"active": 1}
	if filters.branch:
		f["branch"] = filters.branch
	if filters.ward:
		f["ward"] = filters.ward
	beds = frappe.get_list("Hospital Bed", filters=f, fields=["ward", "bed_class", "status", "branch"], limit_page_length=0)
	groups = {}
	for b in beds:
		g = groups.setdefault((b.branch, b.ward, b.bed_class), {"branch": b.branch, "ward": b.ward, "bed_class": b.bed_class, "total": 0, "Occupied": 0, "Available": 0, "Reserved": 0, "Cleaning": 0, "Maintenance": 0})
		g["total"] += 1
		g[b.status] = g.get(b.status, 0) + 1
	rows = sorted(groups.values(), key=lambda g: (g["branch"] or "", g["ward"] or "", g["bed_class"] or ""))
	for g in rows:
		g["usable"] = g["total"] - g["Maintenance"]
		g["occupancy"] = occupancy_pct(g["Occupied"], g["usable"])
	tot = {k: sum(g[k] for g in rows) for k in ("total", "Occupied", "Available", "Reserved", "Cleaning", "Maintenance", "usable")}
	cols = [
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Hospital Branch", "width": 130},
		{"label": _("Ward"), "fieldname": "ward", "fieldtype": "Link", "options": "Ward", "width": 140},
		{"label": _("Bed Class"), "fieldname": "bed_class", "fieldtype": "Data", "width": 110},
		{"label": _("Beds"), "fieldname": "total", "fieldtype": "Int", "width": 70},
		{"label": _("Occupied"), "fieldname": "Occupied", "fieldtype": "Int", "width": 80},
		{"label": _("Available"), "fieldname": "Available", "fieldtype": "Int", "width": 80},
		{"label": _("Reserved"), "fieldname": "Reserved", "fieldtype": "Int", "width": 80},
		{"label": _("Cleaning"), "fieldname": "Cleaning", "fieldtype": "Int", "width": 80},
		{"label": _("Maintenance"), "fieldname": "Maintenance", "fieldtype": "Int", "width": 90},
		{"label": _("Occupancy %"), "fieldname": "occupancy", "fieldtype": "Percent", "width": 100},
	]
	summary = [{"label": _("Occupancy %"), "value": occupancy_pct(tot["Occupied"], tot["usable"]), "datatype": "Percent"}, {"label": _("Beds"), "value": tot["total"], "datatype": "Int"}]
	return cols, rows, None, None, summary
