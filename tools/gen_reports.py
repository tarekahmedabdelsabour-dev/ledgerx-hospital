"""Writes the report JSON files. Run from the repo root. The .py/.js of each report are hand written and never overwritten."""
import json
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "ledgerx_hospital", "hospital", "report")
TS = "2026-11-23 08:00:00.000000"
ROLES = ["Hospital Manager", "Accounts Manager", "Accounts User"]
REPORTS = [
	("Daily Census", "Inpatient Admission", ["Hospital Doctor", "Hospital Nurse", "Hospital Reception"]),
	("Bed Occupancy", "Hospital Bed", ["Hospital Nurse", "Hospital Reception"]),
	("Revenue Analysis", "Hospital Charge", ["Hospital Cashier"]),
	("Unbilled Charges", "Hospital Charge", ["Hospital Cashier", "Hospital Reception"]),
	("Insurance Receivable", "Hospital Bill", ["Hospital Insurance", "Hospital Cashier"]),
	("Appointments Summary", "Patient Appointment", ["Hospital Reception", "Hospital Doctor"]),
	("Lab Turnaround", "Lab Order", ["Hospital Lab"]),
	("Emergency Waiting Times", "Emergency Visit", ["Hospital Doctor", "Hospital Nurse"]),
	("Theatre Utilisation", "Surgery Booking", ["Hospital Doctor"]),
	("Branch Comparison", "Hospital Branch", []),
	("Medication Dispensing", "Medication Dispense", ["Hospital Pharmacist"]),
	("Doctor Fees Due", "Hospital Bill", ["Hospital Cashier"]),
]
for name, ref, extra in REPORTS:
	slug = name.lower().replace(" ", "_")
	folder = os.path.join(BASE, slug)
	os.makedirs(folder, exist_ok=True)
	open(os.path.join(folder, "__init__.py"), "a").close()
	with open(os.path.join(folder, slug + ".json"), "w") as fh:
		json.dump({"add_total_row": 0, "columns": [], "creation": TS, "disabled": 0, "docstatus": 0, "doctype": "Report", "filters": [], "idx": 0, "is_standard": "Yes",
			"modified": TS, "modified_by": "Administrator", "module": "Hospital", "name": name, "owner": "Administrator", "prepared_report": 0, "ref_doctype": ref,
			"report_name": name, "report_type": "Script Report", "roles": [{"role": r} for r in ROLES + extra]}, fh, indent=1)
		fh.write("\n")
print(len(REPORTS), "reports")
