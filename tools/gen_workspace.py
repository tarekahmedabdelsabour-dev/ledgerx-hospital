"""Writes the workspace, sidebar and dock JSON of ledgerx_hospital. Run from the repo root."""
import json
import os
import uuid

BASE = os.path.join(os.path.dirname(__file__), "..", "ledgerx_hospital")
TS = "2026-11-23 09:00:00.000000"  # raise this whenever the workspace changes: migrate only re-reads a file that is newer than the saved one
TODAY = [["Patient Appointment", "appointment_date", "Timespan", "today"], ["Patient Appointment", "status", "!=", "Cancelled"]]
CARDS = [
	("Appointments Today", "Patient Appointment", TODAY, "Count", None),
	("Patients In Hospital", "Inpatient Admission", [["Inpatient Admission", "status", "=", "Admitted"]], "Count", None),
	("Waiting in Emergency", "Emergency Visit", [["Emergency Visit", "status", "=", "Waiting"]], "Count", None),
	("Lab Orders Pending", "Lab Order", [["Lab Order", "status", "in", ["Ordered", "In Progress"]]], "Count", None),
	("Radiology Pending", "Radiology Order", [["Radiology Order", "status", "in", ["Ordered", "Scheduled", "Performed"]]], "Count", None),
	("Surgeries Today", "Surgery Booking", [["Surgery Booking", "scheduled_start", "Timespan", "today"], ["Surgery Booking", "status", "!=", "Cancelled"]], "Count", None),
	("Unbilled Charges", "Hospital Charge", [["Hospital Charge", "status", "=", "Unbilled"]], "Count", None),
	("Approvals Waiting", "Insurance Approval", [["Insurance Approval", "status", "=", "Requested"]], "Count", None),
	("Claims Open", "Insurance Claim", [["Insurance Claim", "status", "in", ["Submitted", "Partially Paid"]]], "Count", None),
]
CHARTS = [
	("Appointments by Status", "Patient Appointment", "Donut", "group", {"by": "status"}),
	("Charges by Service Type", "Hospital Charge", "Donut", "group", {"by": "service_type", "filters": [["Hospital Charge", "status", "!=", "Cancelled"]]}),
	("Emergency by Triage Level", "Emergency Visit", "Donut", "group", {"by": "triage_level"}),
]
GROUPS = [
	("Front Desk", None, 0, [
		("Hospital Patient", "DocType", "Hospital Patient", "user-round"), ("Patient Appointment", "DocType", "Patient Appointment", "calendar-check"),
		("Emergency Visit", "DocType", "Emergency Visit", "siren")]),
	("Clinic", "stethoscope", 0, [
		("Patient Encounter", "DocType", "Patient Encounter", "clipboard-list"), ("Vital Signs", "DocType", "Vital Signs", "activity")]),
	("Inpatients", "bed", 0, [
		("Inpatient Admission", "DocType", "Inpatient Admission", "bed"), ("Nursing Note", "DocType", "Nursing Note", "notebook-pen"),
		("Medication Administration", "DocType", "Medication Administration", "hospital"), ("Hospital Bed", "DocType", "Hospital Bed", "bed-single")]),
	("Diagnostics", "microscope", 0, [
		("Lab Order", "DocType", "Lab Order", "flask-conical"), ("Lab Result", "DocType", "Lab Result", "test-tube"), ("Radiology Order", "DocType", "Radiology Order", "scan")]),
	("Theatre and Hospital", "scissors", 0, [
		("Surgery Booking", "DocType", "Surgery Booking", "scissors"), ("Medication Dispense", "DocType", "Medication Dispense", "pill-bottle")]),
	("Billing", "receipt", 0, [
		("Hospital Charge", "DocType", "Hospital Charge", "receipt"), ("Hospital Bill", "DocType", "Hospital Bill", "file-text")]),
	("Insurance", "shield", 0, [
		("Hospital Insurer", "DocType", "Hospital Insurer", "building"), ("Hospital Insurance Plan", "DocType", "Hospital Insurance Plan", "id-card"),
		("Insurance Approval", "DocType", "Insurance Approval", "badge-check"), ("Insurance Claim", "DocType", "Insurance Claim", "folder-open")]),
	("Doctors", "user-round-check", 0, [
		("Hospital Doctor", "DocType", "Hospital Doctor", "stethoscope"), ("Doctor Statement", "DocType", "Doctor Statement", "wallet")]),
	("Reports", "bar-chart-3", 0, [
		("Daily Census", "Report", "Daily Census", "list"), ("Bed Occupancy", "Report", "Bed Occupancy", "bed"), ("Revenue Analysis", "Report", "Revenue Analysis", "bar-chart-3"),
		("Unbilled Charges", "Report", "Unbilled Charges", "receipt"), ("Insurance Receivable", "Report", "Hospital Insurance Receivable", "banknote"),
		("Appointments Summary", "Report", "Appointments Summary", "calendar-check"), ("Lab Turnaround", "Report", "Lab Turnaround", "timer"),
		("Emergency Waiting Times", "Report", "Emergency Waiting Times", "siren"), ("Theatre Utilisation", "Report", "Theatre Utilisation", "scissors"),
		("Branch Comparison", "Report", "Branch Comparison", "git-compare"), ("Medication Dispensing", "Report", "Medication Dispensing", "hospital"),
		("Doctor Fees Due", "Report", "Doctor Fees Due", "wallet")]),
	("Setup", "settings", 0, [
		("Hospital Settings", "DocType", "Hospital Settings", "settings"), ("Hospital Branch", "DocType", "Hospital Branch", "hospital"),
		("Hospital Department", "DocType", "Hospital Department", "network"), ("Medical Specialty", "DocType", "Medical Specialty", "graduation-cap"),
		("Hospital Service", "DocType", "Hospital Service", "list-checks"), ("Ward", "DocType", "Ward", "door-open"), ("Operating Room", "DocType", "Operating Room", "scissors"),
		("Lab Test Template", "DocType", "Lab Test Template", "flask-conical")]),
	("Source Data", "database", 1, [
		("Item", "DocType", "Item", "box"), ("Customer", "DocType", "Customer", "users"), ("Supplier", "DocType", "Supplier", "truck"), ("Warehouse", "DocType", "Warehouse", "warehouse"),
		("Stock Entry", "DocType", "Stock Entry", "package"), ("Sales Invoice", "DocType", "Sales Invoice", "file-text"), ("Payment Entry", "DocType", "Payment Entry", "banknote"),
		("Price List", "DocType", "Price List", "tag")]),
]
TOP = ["Hospital Patient", "Patient Appointment", "Emergency Visit", "Inpatient Admission"]


def write(path, data):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as fh:
		json.dump(data, fh, indent=1, ensure_ascii=False)
		fh.write("\n")


def slug(n):
	return n.lower().replace(" ", "_").replace("-", "_")


def write_cards():
	for label, dt, flt, fn, _f in CARDS:
		write(os.path.join(BASE, "hospital", "number_card", slug(label), slug(label) + ".json"), {
			"creation": TS, "docstatus": 0, "doctype": "Number Card", "document_type": dt, "filters_json": json.dumps(flt), "function": fn,
			"idx": 0, "is_public": 1, "is_standard": 1, "label": label, "modified": TS, "modified_by": "Administrator", "module": "Hospital",
			"name": label, "owner": "Administrator", "show_percentage_stats": 0, "stats_time_interval": "Daily", "type": "Document Type"})
	for name, dt, typ, kind, x in CHARTS:
		d = {"chart_name": name, "creation": TS, "docstatus": 0, "doctype": "Dashboard Chart", "document_type": dt, "dynamic_filters_json": "",
			"idx": 0, "is_public": 1, "is_standard": 1, "modified": TS, "modified_by": "Administrator", "module": "Hospital", "name": name,
			"number_of_groups": 0, "owner": "Administrator", "type": typ, "use_report_chart": 0, "y_axis": []}
		if kind == "group":
			d.update({"chart_type": "Group By", "group_by_based_on": x["by"], "group_by_type": "Count", "filters_json": json.dumps(x.get("filters", [])), "timeseries": 0})
		else:
			d.update({"chart_type": "Count", "based_on": x["based_on"], "filters_json": json.dumps(x["filters"]), "time_interval": x.get("interval", "Monthly"),
				"timeseries": 1, "timespan": x.get("timespan", "Last Year")})
		write(os.path.join(BASE, "hospital", "dashboard_chart", slug(name), slug(name) + ".json"), d)


def main():
	write_cards()
	rid = lambda: uuid.uuid4().hex[:10]
	content = [{"id": rid(), "type": "header", "data": {"text": '<span class="h4"><b>Hospital</b></span>', "col": 12}}]
	for label, *_r in CARDS:
		content.append({"id": rid(), "type": "number_card", "data": {"number_card_name": label, "col": 3}})
	for name, *_r in CHARTS:
		content.append({"id": rid(), "type": "chart", "data": {"chart_name": name, "col": 6}})
	shortcuts, links = [], []
	for label in TOP:
		content.insert(1 + len(shortcuts), {"id": rid(), "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
		kind = "DocType"
		sc = {"label": label, "link_to": label, "type": kind}
		if kind == "DocType":
			sc["doc_view"] = "List"
		else:
			sc["is_query_report"] = 1
		shortcuts.append(sc)
	for title, _i, _c, items in GROUPS:
		content.append({"id": rid(), "type": "card", "data": {"card_name": title, "col": 4}})
		links.append({"type": "Card Break", "label": title, "hidden": 0, "is_query_report": 0, "link_count": len(items), "onboard": 0})
		for label, kind, target, _icon in items:
			links.append({"type": "Link", "label": label, "link_type": kind, "link_to": target, "hidden": 0, "is_query_report": 1 if kind == "Report" else 0,
				"onboard": 0, "dependencies": "", "only_for": ""})
	write(os.path.join(BASE, "hospital", "workspace", "hospital", "hospital.json"), {
		"charts": [{"chart_name": c[0], "label": c[0]} for c in CHARTS], "content": json.dumps(content), "creation": TS, "custom_blocks": [], "docstatus": 0, "doctype": "Workspace",
		"for_user": "", "hide_custom": 1, "icon": "hospital", "idx": 1, "is_hidden": 0, "label": "Hospital", "links": links, "title": "Hospital", "modified": TS,
		"modified_by": "Administrator", "module": "Hospital", "name": "Hospital", "number_cards": [{"label": c[0], "number_card_name": c[0]} for c in CARDS], "owner": "Administrator",
		"parent_page": "", "public": 1, "quick_lists": [], "roles": [], "sequence_id": 32.0, "shortcuts": shortcuts})
	def row(i, label, kind, target, icon, child):
		d = {"child": child, "collapsible": 1, "doctype": "Sidebar Item", "icon": icon, "idx": i, "indent": 0, "keep_closed": 0, "label": label,
			"parentfield": "items", "parenttype": "Sidebar", "show_arrow": 0, "type": "Link"}
		if kind == "URL":
			d.update({"link_type": "URL", "url": target, "open_in_new_tab": 1})
		else:
			d.update({"link_to": target, "link_type": kind})
		return d
	items = [row(1, "Home", "Workspace", "Hospital", "house", 0)]
	for title, icon, closed, entries in GROUPS:
		if icon:
			items.append({"child": 0, "collapsible": 1, "doctype": "Sidebar Item", "icon": icon, "idx": len(items) + 1, "indent": 1, "keep_closed": closed,
				"label": title, "link_type": "DocType", "parentfield": "items", "parenttype": "Sidebar", "show_arrow": 0, "type": "Section Break"})
		for label, kind, target, ic in entries:
			items.append(row(len(items) + 1, label, kind, target, ic, 1 if icon else 0))
	write(os.path.join(BASE, "sidebar", "hospital", "hospital.json"), {"app": "ledgerx_hospital", "doctype": "Sidebar", "header_icon": "hospital",
		"items": items, "module": "Hospital", "name": "Hospital", "standard": 1, "title": "Hospital"})
	write(os.path.join(BASE, "dock", "hospital", "hospital.json"), {"app": "ledgerx_hospital", "creation": TS, "docstatus": 0, "doctype": "Dock", "idx": 0,
		"items": [{"added": 0, "hidden": 0, "icon": "hospital", "link_to": "Hospital", "link_type": "Sidebar", "title": "Hospital"}],
		"modified": TS, "modified_by": "Administrator", "name": "hospital", "owner": "Administrator", "standard": 1})


main()
