import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, nowdate

from ledgerx_hospital.engine import triage


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"arrival_time": ["between", [filters.from_date or add_days(nowdate(), -30), (filters.to_date or nowdate()) + " 23:59:59"]]}
	if filters.branch:
		f["branch"] = filters.branch
	visits = frappe.get_list("Emergency Visit", filters=f, fields=["triage_level", "arrival_time", "seen_at", "status"], limit_page_length=0)
	groups = {}
	for v in visits:
		g = groups.setdefault(v.triage_level or "-", {"level": v.triage_level or "-", "visits": 0, "seen": 0, "waits": [], "within": 0, "left": 0})
		g["visits"] += 1
		if v.status == "Left Without Being Seen":
			g["left"] += 1
		if v.seen_at:
			w = triage.wait_minutes(get_datetime(v.arrival_time), get_datetime(v.seen_at), get_datetime(v.seen_at))
			g["seen"] += 1
			g["waits"].append(w)
			if v.triage_level and w <= triage.TARGETS.get(int(v.triage_level), 120):
				g["within"] += 1
	rows = []
	for k in sorted(groups):
		g = groups[k]
		w = g["waits"]
		rows.append({"level": g["level"], "color": triage.COLORS.get(int(k)) if k != "-" else "", "visits": g["visits"], "seen": g["seen"], "left": g["left"], "avg_wait": round(sum(w) / len(w), 1) if w else 0,
			"worst": max(w) if w else 0, "target": triage.TARGETS.get(int(k)) if k != "-" else None, "within_pct": round(g["within"] * 100.0 / g["seen"], 1) if g["seen"] and k != "-" else None})
	cols = [{"label": _("Triage Level"), "fieldname": "level", "fieldtype": "Data", "width": 90}, {"label": _("Colour"), "fieldname": "color", "fieldtype": "Data", "width": 80},
		{"label": _("Visits"), "fieldname": "visits", "fieldtype": "Int", "width": 70}, {"label": _("Seen"), "fieldname": "seen", "fieldtype": "Int", "width": 70},
		{"label": _("Left Unseen"), "fieldname": "left", "fieldtype": "Int", "width": 100}, {"label": _("Average Wait (min)"), "fieldname": "avg_wait", "fieldtype": "Float", "width": 130},
		{"label": _("Longest Wait (min)"), "fieldname": "worst", "fieldtype": "Int", "width": 130}, {"label": _("Target (min)"), "fieldname": "target", "fieldtype": "Int", "width": 100},
		{"label": _("Seen Within Target %"), "fieldname": "within_pct", "fieldtype": "Percent", "width": 140}]
	return cols, rows
