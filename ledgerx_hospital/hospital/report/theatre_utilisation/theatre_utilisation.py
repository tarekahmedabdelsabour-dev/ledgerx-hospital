import frappe
from frappe import _
from frappe.utils import add_days, date_diff, get_datetime, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frm, to = filters.from_date or add_days(nowdate(), -30), filters.to_date or nowdate()
	hours = float(filters.day_hours or 10)
	f = {"status": ["in", ["Booked", "Pre-op Ready", "In Progress", "Completed"]], "scheduled_start": ["between", [frm, to + " 23:59:59"]]}
	if filters.branch:
		f["branch"] = filters.branch
	cases = frappe.get_list("Surgery Booking", filters=f, fields=["operating_room", "status", "scheduled_start", "scheduled_end", "actual_start", "actual_end", "branch"], limit_page_length=0)
	days = max(date_diff(to, frm) + 1, 1)
	rooms = {}
	for c in cases:
		s, e = (get_datetime(c.actual_start), get_datetime(c.actual_end)) if (c.actual_start and c.actual_end) else (get_datetime(c.scheduled_start), get_datetime(c.scheduled_end))
		g = rooms.setdefault(c.operating_room, {"room": c.operating_room, "branch": c.branch, "cases": 0, "completed": 0, "minutes": 0})
		g["cases"] += 1
		g["completed"] += 1 if c.status == "Completed" else 0
		g["minutes"] += max(int((e - s).total_seconds() // 60), 0)
	rows = []
	for g in sorted(rooms.values(), key=lambda x: x["room"] or ""):
		avail = days * hours * 60
		g["hours"] = round(g["minutes"] / 60.0, 1)
		g["utilisation"] = round(min(g["minutes"] * 100.0 / avail, 100.0), 1) if avail else 0
		rows.append(g)
	cols = [{"label": _("Operating Room"), "fieldname": "room", "fieldtype": "Link", "options": "Operating Room", "width": 170}, {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Hospital Branch", "width": 130},
		{"label": _("Cases"), "fieldname": "cases", "fieldtype": "Int", "width": 70}, {"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 90},
		{"label": _("Hours Used"), "fieldname": "hours", "fieldtype": "Float", "width": 100}, {"label": _("Utilisation %"), "fieldname": "utilisation", "fieldtype": "Percent", "width": 110}]
	return cols, rows
