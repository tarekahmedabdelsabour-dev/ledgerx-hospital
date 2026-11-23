"""Builds every DocType JSON of ledgerx_hospital from the compact tables below.
Run from the repo root:  python3 tools/gen_doctypes.py   (rewrites ledgerx_hospital/hospital/doctype/*/*.json; controller .py files are never overwritten)"""
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "ledgerx_hospital", "hospital", "doctype")
TS = "2026-11-22 22:00:00.000000"
MODULE = "Hospital"
MGR, DOC, NUR, REC, LAB, RAD, PHM, CSH, INS = ("Hospital Manager", "Hospital Doctor", "Hospital Nurse", "Hospital Reception", "Hospital Lab",
	"Hospital Radiology", "Hospital Pharmacist", "Hospital Cashier", "Hospital Insurance")
ROLES = [MGR, DOC, NUR, REC, LAB, RAD, PHM, CSH, INS]


def f(name, ftype, label=None, **kw):
	d = {"fieldname": name, "fieldtype": ftype}
	if ftype not in ("Section Break", "Column Break", "Tab Break"):
		d["label"] = label or name.replace("_", " ").title()
	elif label:
		d["label"] = label
	d.update(kw)
	return d


def sec(name, label=None, **kw):
	return f(name, "Section Break", label, **kw)


def col(name):
	return f(name, "Column Break")


def perms(*rows):
	"""mode: r | rw | rwc | all | sub (rwc + submit) | full (all + submit/cancel/amend)"""
	out = []
	for role, mode in rows:
		p = {"role": role, "read": 1, "report": 1, "print": 1, "export": 1}
		if mode in ("rw", "rwc", "all", "sub", "full"):
			p["write"] = 1
		if mode in ("rwc", "all", "sub", "full"):
			p["create"] = 1
		if mode in ("all", "full"):
			p["delete"] = 1
		if mode in ("sub", "full"):
			p["submit"] = 1
		if mode == "full":
			p.update({"cancel": 1, "amend": 1})
		out.append(p)
	out.append({"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "print": 1, "export": 1})
	return out


DT = {}


def doctype(name, fields, **kw):
	DT[name] = {"name": name, "fields": fields, **kw}


def S(*opts):
	return "\n".join(opts)


CLINICAL_READ = [(MGR, "r"), (DOC, "r"), (NUR, "r"), (REC, "r"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")]
CHART = [(MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "r"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")]
MASTER = [(MGR, "all"), (DOC, "r"), (NUR, "r"), (REC, "r"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")]
STATUS = S("Draft", "Active", "Inactive")
SERVICE_TYPES = S("Consultation", "Procedure", "Laboratory", "Radiology", "Surgery", "Anesthesia", "Room", "Nursing", "Emergency", "Pharmacy", "Package", "Other")

# ================================================================== settings and masters
doctype("Hospital Settings", [
	f("company", "Link", "Default Company", options="Company"),
	f("price_list", "Link", "Cash Price List", options="Price List", description="Prices for patients without insurance. Insurance plans can have their own price list."),
	f("service_item_group", "Link", "Item Group for Service Items", options="Item Group", description="Each hospital service gets a non-stock item in this group."),
	f("sales_taxes_template", "Link", "Sales Taxes Template", options="Sales Taxes and Charges Template", description="Leave empty when medical services are exempt."),
	sec("sb_visit", "Clinics"),
	f("appointment_minutes", "Int", "Default Appointment Length (minutes)", default=15),
	f("followup_days", "Int", "Follow-up Window (days)", default=14, description="A repeat visit to the same doctor inside this window is a follow-up."),
	f("followup_fee_pct", "Percent", "Follow-up Fee (% of the consultation)", default=0, description="0 = follow-ups are free."),
	f("allow_overbooking", "Check", "Allow Booking a Full Slot", default=0),
	sec("sb_adm", "Inpatients"),
	f("bed_cutoff_hour", "Int", "Bed-day Cutoff Hour (0-23)", default=12, description="A bed-day is counted each time the stay passes this hour."),
	f("bed_min_days", "Int", "Minimum Bed-days per Admission", default=1),
	f("post_bed_charges", "Check", "Post Bed Charges Automatically Every Day", default=1),
	f("require_deposit", "Check", "Warn When an Admission Has No Deposit", default=0),
	sec("sb_or", "Surgery"),
	f("or_buffer_minutes", "Int", "Cleaning Time Between Cases (minutes)", default=30),
	f("preop", "Table", "Pre-operative Checklist", options="Preop Template Item", description="Copied to every new surgery booking."),
	sec("sb_fee", "Doctor Fees"),
	f("commission_basis", "Select", "Doctor Earns When the Bill Is", options=S("Invoiced", "Paid"), default="Invoiced"),
	f("doctor_fee_item", "Link", "Item for Doctor Payments", options="Item", description="A non-stock item used on the purchase invoice of a doctor statement. Created automatically."),
	f("doctor_expense_account", "Link", "Doctor Fees Expense Account", options="Account"),
	f("claim_writeoff_account", "Link", "Rejected Claims Write-off Account", options="Account", description="Used when you write off the part of a claim the insurer refused."),
	sec("sb_walk", "Patients"),
	f("walk_in_customer", "Link", "Customer for Unidentified Patients", options="Customer"),
	f("require_national_id", "Check", "Require National ID", default=0),
], issingle=1, icon="fa fa-hospital-o", perms=perms((MGR, "rw")) + [{"role": r, "read": 1} for r in ROLES if r != MGR])

doctype("Preop Template Item", [f("check_item", "Data", "Check", reqd=1, in_list_view=1)], istable=1)

doctype("Hospital Branch", [
	f("branch_name", "Data", "Branch Name", reqd=1, unique=1, in_list_view=1),
	f("company", "Link", "Company", options="Company", reqd=1, in_list_view=1, description="A group can use one company per branch or one for all and a cost center per branch."),
	f("cost_center", "Link", "Cost Center", options="Cost Center"),
	col("cb1"),
	f("warehouse", "Link", "Pharmacy Warehouse", options="Warehouse", reqd=1, description="Medicines are dispensed from here."),
	f("or_warehouse", "Link", "Operating Theatre Warehouse", options="Warehouse", description="Surgery consumables are issued from here. Empty = the pharmacy warehouse."),
	f("price_list", "Link", "Price List", options="Price List", description="Overrides the cash price list for this branch."),
	f("active", "Check", "Active", default=1),
	sec("sb2", "Contact"),
	f("address", "Small Text", "Address"),
	f("phone", "Data", "Phone"),
], autoname="field:branch_name", icon="fa fa-building", perms=perms((MGR, "all")) + [{"role": r, "read": 1} for r in ROLES if r != MGR])

doctype("Medical Specialty", [f("specialty", "Data", "Specialty", reqd=1, unique=1)], autoname="field:specialty", icon="fa fa-stethoscope", perms=perms(*MASTER))
doctype("Hospital Department", [
	f("department_name", "Data", "Department", reqd=1, unique=1, in_list_view=1),
	f("department_type", "Select", "Type", options=S("Clinical", "Support", "Administrative"), default="Clinical", in_list_view=1),
	f("cost_center", "Link", "Cost Center", options="Cost Center"),
	f("active", "Check", "Active", default=1),
], autoname="field:department_name", icon="fa fa-sitemap", perms=perms(*MASTER))

doctype("Hospital Service", [
	f("service_code", "Data", "Code", reqd=1, unique=1, in_list_view=1),
	f("service_name", "Data", "Service", reqd=1, in_list_view=1),
	f("service_type", "Select", "Type", options=SERVICE_TYPES, reqd=1, in_list_view=1, in_standard_filter=1),
	f("department", "Link", "Department", options="Hospital Department", in_standard_filter=1),
	col("cb1"),
	f("base_price", "Currency", "Cash Price", reqd=1, in_list_view=1, description="Kept in the cash price list. Insurance plans use their own price list when they have one."),
	f("item", "Link", "Billing Item", options="Item", read_only=1, description="Created automatically; the invoices use it."),
	f("duration_minutes", "Int", "Duration (minutes)"),
	f("needs_doctor", "Check", "Needs a Doctor", default=0),
	f("active", "Check", "Active", default=1),
	sec("sb2", "Notes"),
	f("description", "Small Text", "Description"),
], autoname="field:service_code", title_field="service_name", show_title_field_in_link=1, search_fields="service_name,service_type", icon="fa fa-list-alt",
	perms=perms(*MASTER))

doctype("Doctor Branch", [f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_list_view=1)], istable=1)
doctype("Doctor Schedule", [
	f("weekday", "Select", "Day", options=S("Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"), reqd=1, in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch", in_list_view=1),
	f("from_time", "Time", "From", reqd=1, in_list_view=1),
	f("to_time", "Time", "To", reqd=1, in_list_view=1),
	f("slot_minutes", "Int", "Slot (minutes)", default=15, reqd=1, in_list_view=1),
	f("capacity", "Int", "Patients per Slot", default=1),
], istable=1)
doctype("Doctor Time Off", [
	f("from_date", "Date", "From", reqd=1, in_list_view=1), f("to_date", "Date", "To", in_list_view=1), f("reason", "Data", "Reason", in_list_view=1)], istable=1)
doctype("Doctor Fee Rule", [
	f("service", "Link", "Service", options="Hospital Service", in_list_view=1),
	f("service_type", "Select", "Service Type", options="\n" + SERVICE_TYPES, in_list_view=1),
	f("payer", "Select", "Patient Pays", options=S("All", "Cash", "Insurance"), default="All", in_list_view=1),
	f("mode", "Select", "Fee Is", options=S("Percent", "Fixed"), default="Percent", reqd=1, in_list_view=1),
	f("value", "Float", "Value", reqd=1, in_list_view=1, description="Percent of the net amount, or a fixed amount per unit."),
], istable=1)

doctype("Hospital Doctor", [
	f("doctor_name", "Data", "Doctor Name", reqd=1, in_list_view=1),
	f("specialty", "Link", "Specialty", options="Medical Specialty", in_list_view=1, in_standard_filter=1),
	f("department", "Link", "Department", options="Hospital Department"),
	f("default_branch", "Link", "Main Branch", options="Hospital Branch", in_standard_filter=1),
	col("cb1"),
	f("employee", "Link", "Employee", options="Employee", description="Links the doctor to the staff records."),
	f("user", "Link", "User", options="User", description="The doctor's login. Needed to alert the doctor about critical results."),
	f("supplier", "Link", "Supplier (for payments)", options="Supplier", description="Doctor statements are paid through a purchase invoice to this supplier."),
	f("mobile", "Data", "Mobile"),
	f("license_no", "Data", "License No."),
	f("consultation_service", "Link", "Consultation Service", options="Hospital Service", description="Priced as the consultation fee of this doctor."),
	f("followup_days", "Int", "Follow-up Window (days)", description="Empty = the hospital setting."),
	f("active", "Check", "Active", default=1, in_standard_filter=1),
	sec("sb2", "Branches"),
	f("branches", "Table", "Works In", options="Doctor Branch"),
	sec("sb3", "Weekly Schedule"),
	f("schedule", "Table", "Schedule", options="Doctor Schedule"),
	f("time_off", "Table", "Time Off", options="Doctor Time Off"),
	sec("sb4", "Fees"),
	f("fee_rules", "Table", "Fee Rules", options="Doctor Fee Rule", description="The most specific rule wins: a rule for the service, then for the service type, then a general rule."),
], autoname="format:DOC-.####", title_field="doctor_name", show_title_field_in_link=1, search_fields="specialty,mobile", icon="fa fa-user-md",
	perms=perms((MGR, "all"), (DOC, "r"), (NUR, "r"), (REC, "rw"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")))

doctype("Ward", [
	f("ward_name", "Data", "Ward", reqd=1, in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_list_view=1, in_standard_filter=1),
	f("ward_type", "Select", "Type", options=S("General", "Semi-private", "Private", "VIP", "ICU", "NICU", "CCU", "Isolation", "Recovery", "Emergency", "Maternity", "Pediatric"),
		default="General", in_list_view=1, in_standard_filter=1),
	f("department", "Link", "Department", options="Hospital Department"),
	f("floor", "Data", "Floor"),
	f("active", "Check", "Active", default=1),
], autoname="format:WRD-.#####", title_field="ward_name", show_title_field_in_link=1, icon="fa fa-bed", perms=perms(*MASTER))

BED_STATUS = S("Available", "Occupied", "Reserved", "Cleaning", "Maintenance")
doctype("Hospital Bed", [
	f("bed_no", "Data", "Bed No.", reqd=1, in_list_view=1),
	f("ward", "Link", "Ward", options="Ward", reqd=1, in_list_view=1, in_standard_filter=1),
	f("branch", "Link", "Branch", options="Hospital Branch", read_only=1, fetch_from="ward.branch", in_standard_filter=1),
	f("room_no", "Data", "Room"),
	col("cb1"),
	f("bed_class", "Select", "Class", options=S("Standard", "Semi-private", "Private", "VIP", "ICU", "NICU", "Isolation"), default="Standard", in_list_view=1),
	f("charge_service", "Link", "Daily Charge Service", options="Hospital Service", reqd=1, description="A service of type Room. Its price is the daily rate."),
	f("status", "Select", "Status", options=BED_STATUS, default="Available", in_list_view=1, in_standard_filter=1),
	f("current_admission", "Link", "Current Admission", options="Inpatient Admission", read_only=1),
	f("active", "Check", "Active", default=1),
], autoname="format:BED-.#####", title_field="bed_no", show_title_field_in_link=1, search_fields="ward,room_no", icon="fa fa-bed", perms=perms((MGR, "all"), (DOC, "r"), (NUR, "rw"),
	(REC, "rw"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")))

doctype("Operating Room", [
	f("room_name", "Data", "Operating Room", reqd=1, in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_list_view=1, in_standard_filter=1),
	f("room_type", "Select", "Type", options=S("General", "Cardiac", "Orthopedic", "Neuro", "Obstetric", "Minor", "Endoscopy"), default="General"),
	f("status", "Select", "Status", options=S("Available", "Cleaning", "Maintenance"), default="Available", in_list_view=1),
	f("hourly_service", "Link", "Theatre Time Service", options="Hospital Service", description="Charged per hour of the actual case, rounded up to the half hour."),
], autoname="format:ORM-.####", title_field="room_name", show_title_field_in_link=1, icon="fa fa-medkit", perms=perms(*MASTER))

# ================================================================== insurance
doctype("Hospital Insurer", [
	f("company_name", "Data", "Insurance Company", reqd=1, unique=1, in_list_view=1),
	f("customer", "Link", "Customer (receivable account)", options="Customer", read_only=1, description="Created automatically: the insurer's invoices are issued to it."),
	f("claim_days", "Int", "Days to Pay a Claim", default=60),
	f("contact", "Small Text", "Contact"),
	f("active", "Check", "Active", default=1, in_list_view=1),
], autoname="field:company_name", icon="fa fa-shield", perms=perms((MGR, "all"), (INS, "rwc"), (DOC, "r"), (NUR, "r"), (REC, "r"), (CSH, "r"), (LAB, "r"), (RAD, "r"), (PHM, "r")))

doctype("Plan Rule", [
	f("service", "Link", "Service", options="Hospital Service", in_list_view=1),
	f("service_type", "Select", "Service Type", options="\n" + SERVICE_TYPES, in_list_view=1),
	f("cover_pct", "Percent", "Insurer Pays %", in_list_view=1, description="Empty = the plan's default."),
	f("copay_fixed", "Currency", "Patient Fixed Co-pay per Line"),
	f("line_cap", "Currency", "Insurer Maximum per Line"),
	f("requires_approval", "Check", "Needs Prior Approval", in_list_view=1),
	f("excluded", "Check", "Not Covered", in_list_view=1),
], istable=1)

doctype("Hospital Insurance Plan", [
	f("plan_name", "Data", "Plan", reqd=1, unique=1, in_list_view=1),
	f("insurance_company", "Link", "Insurance Company", options="Hospital Insurer", reqd=1, in_list_view=1, in_standard_filter=1),
	f("price_list", "Link", "Price List", options="Price List", description="The contract prices. Empty = the cash price list."),
	f("active", "Check", "Active", default=1, in_list_view=1),
	col("cb1"),
	f("valid_from", "Date", "Valid From"),
	f("valid_to", "Date", "Valid To"),
	sec("sb_cov", "Coverage"),
	f("cover_pct", "Percent", "Insurer Pays % (default)", default=80, reqd=1),
	f("discount_pct", "Percent", "Discount Off Cash Prices", description="Used for services that have no price in this plan's price list."),
	f("patient_cap", "Currency", "Patient Maximum per Bill", description="What the patient pays on covered lines never goes above this. Empty = no maximum."),
	f("visit_copay", "Currency", "Patient Minimum per Bill (visit co-pay)"),
	f("annual_limit", "Currency", "Annual Limit per Member", description="Empty = no limit."),
	sec("sb_rules", "Rules by Service"),
	f("rules", "Table", "Rules", options="Plan Rule", description="A rule for a service beats a rule for its type, which beats the default above."),
], autoname="field:plan_name", icon="fa fa-id-card", perms=perms((MGR, "all"), (INS, "all"), (DOC, "r"), (NUR, "r"), (REC, "r"), (CSH, "r"), (LAB, "r"), (RAD, "r"), (PHM, "r")))

doctype("Approval Service", [
	f("service", "Link", "Service", options="Hospital Service", reqd=1, in_list_view=1),
	f("max_amount", "Currency", "Approved Up To", in_list_view=1, description="Empty = no maximum for this service."),
], istable=1)

doctype("Insurance Approval", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan", reqd=1, in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch"),
	f("requested_on", "Date", "Requested On", default="Today"),
	col("cb1"),
	f("status", "Select", "Status", options=S("Requested", "Approved", "Partially Approved", "Rejected", "Expired"), default="Requested", in_list_view=1, in_standard_filter=1),
	f("approval_no", "Data", "Insurer Approval No."),
	f("valid_till", "Date", "Valid Until"),
	sec("sb2", "Approved Services"),
	f("services", "Table", "Services", options="Approval Service", description="An approval covers these services. Charges for them count as approved while it is valid."),
	f("document", "Attach", "Approval Document"),
	f("notes", "Small Text", "Notes"),
], autoname="format:APR-.YYYY.-.#####", title_field="patient", icon="fa fa-check-square-o", perms=perms((MGR, "all"), (INS, "all"), (DOC, "rwc"), (REC, "rwc"), (CSH, "r"), (NUR, "r")))

# ================================================================== patients
doctype("Hospital Patient", [
	f("patient_name", "Data", "Full Name", reqd=1, in_list_view=1),
	f("gender", "Select", "Gender", options=S("", "Male", "Female"), reqd=1, in_list_view=1, in_standard_filter=1),
	f("date_of_birth", "Date", "Date of Birth", in_list_view=1),
	f("age", "Data", "Age", read_only=1),
	col("cb1"),
	f("national_id", "Data", "National ID", unique=0, in_standard_filter=1, description="14 digits. The birth date and gender are read from it."),
	f("passport_no", "Data", "Passport No."),
	f("mobile", "Data", "Mobile", in_list_view=1, in_standard_filter=1),
	f("email", "Data", "Email", options="Email"),
	f("status", "Select", "Status", options=S("Active", "Inactive", "Deceased"), default="Active", in_standard_filter=1),
	f("photo", "Attach Image", "Photo"),
	sec("sb_addr", "Address"),
	f("address", "Small Text", "Address"),
	f("city", "Data", "City"),
	col("cb2"),
	f("marital_status", "Select", "Marital Status", options=S("", "Single", "Married", "Divorced", "Widowed")),
	f("blood_group", "Select", "Blood Group", options=S("", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")),
	sec("sb_med", "Medical Background"),
	f("allergies", "Small Text", "Allergies", description="One per line or separated by commas. Prescriptions are checked against this list."),
	f("chronic_conditions", "Small Text", "Chronic Conditions"),
	f("medical_notes", "Small Text", "Notes"),
	sec("sb_ins", "Insurance"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan", in_standard_filter=1),
	f("member_no", "Data", "Member No."),
	f("insurance_expiry", "Date", "Card Expires On"),
	sec("sb_em", "Emergency Contact"),
	f("emergency_name", "Data", "Name"),
	f("emergency_phone", "Data", "Phone"),
	f("emergency_relation", "Data", "Relation"),
	sec("sb_sys", "System"),
	f("branch", "Link", "Registered At", options="Hospital Branch"),
	f("customer", "Link", "Customer (billing)", options="Customer", read_only=1, description="Created automatically; invoices and payments use it."),
	f("deceased_on", "Datetime", "Deceased On", depends_on="eval:doc.status=='Deceased'"),
	f("crm_lead", "Data", "CRM Lead"),
], autoname="format:PAT-.#####", title_field="patient_name", show_title_field_in_link=1, search_fields="national_id,mobile", icon="fa fa-user",
	perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "rwc"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")), track_changes=1)

doctype("Vital Signs", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("recorded_at", "Datetime", "Recorded At", reqd=1, default="Now", in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch"),
	f("encounter", "Link", "Encounter", options="Patient Encounter"),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("emergency_visit", "Link", "Emergency Visit", options="Emergency Visit"),
	sec("sb_v", "Readings"),
	f("sys_bp", "Int", "Systolic BP (mmHg)"),
	f("dia_bp", "Int", "Diastolic BP (mmHg)"),
	f("pulse", "Int", "Pulse (/min)"),
	f("resp_rate", "Int", "Respiratory Rate (/min)"),
	col("cb1"),
	f("spo2", "Int", "SpO2 (%)"),
	f("temperature", "Float", "Temperature (C)", precision=1),
	f("blood_glucose", "Float", "Blood Glucose (mg/dL)"),
	f("pain_score", "Int", "Pain (0-10)"),
	sec("sb_b", "Body"),
	f("weight", "Float", "Weight (kg)"),
	f("height", "Float", "Height (cm)"),
	col("cb2"),
	f("bmi", "Float", "BMI", read_only=1, precision=1),
	f("bmi_band", "Data", "BMI Band", read_only=1),
	sec("sb_f", "Review"),
	f("range_flags", "Small Text", "Outside Normal Range", read_only=1, description="A highlight against the ranges in the settings. It is not a diagnosis."),
	f("notes", "Small Text", "Notes"),
	f("recorded_by", "Link", "Recorded By", options="User", read_only=1),
], autoname="format:VIT-.YYYY.-.######", title_field="patient", icon="fa fa-heartbeat", perms=perms(*CHART))

# ================================================================== outpatient
doctype("Patient Appointment", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("doctor", "Link", "Doctor", options="Hospital Doctor", reqd=1, in_list_view=1, in_standard_filter=1),
	f("doctor_name", "Data", "Doctor Name", read_only=1, fetch_from="doctor.doctor_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	col("cb1"),
	f("appointment_date", "Date", "Date", reqd=1, in_list_view=1, in_standard_filter=1),
	f("from_time", "Time", "From", reqd=1, in_list_view=1),
	f("to_time", "Time", "To", reqd=1),
	f("appointment_type", "Select", "Type", options=S("Consultation", "Follow-up", "Procedure", "Telemedicine"), default="Consultation"),
	f("status", "Select", "Status", options=S("Scheduled", "Checked In", "In Consultation", "Completed", "Cancelled", "No Show"), default="Scheduled", in_list_view=1, in_standard_filter=1),
	f("queue_no", "Int", "Queue No.", read_only=1, in_list_view=1),
	sec("sb_fee", "Fee"),
	f("service", "Link", "Service", options="Hospital Service", description="Empty = the doctor's consultation service."),
	f("is_follow_up", "Check", "Follow-up", read_only=1),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	col("cb2"),
	f("checked_in_at", "Datetime", "Checked In At", read_only=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1),
	f("encounter", "Link", "Encounter", options="Patient Encounter", read_only=1),
	sec("sb_n", "Notes"),
	f("reason", "Small Text", "Reason for Visit"),
	f("cancel_reason", "Small Text", "Cancellation Reason"),
], autoname="format:APT-.YYYY.-.#####", title_field="patient_name", icon="fa fa-calendar", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "all"), (CSH, "r"), (INS, "r")), track_changes=1)

doctype("Encounter Diagnosis", [
	f("icd_code", "Data", "ICD Code", in_list_view=1), f("diagnosis", "Data", "Diagnosis", reqd=1, in_list_view=1),
	f("diagnosis_type", "Select", "Type", options=S("Primary", "Secondary", "Provisional"), default="Primary", in_list_view=1)], istable=1)
doctype("Encounter Prescription", [
	f("item_code", "Link", "Medicine", options="Item", reqd=1, in_list_view=1),
	f("drug_name", "Data", "Name", read_only=1, in_list_view=1),
	f("dosage", "Data", "Dose", in_list_view=1), f("frequency", "Data", "Frequency", in_list_view=1),
	f("duration_days", "Int", "Days", in_list_view=1), f("qty", "Float", "Quantity to Dispense", default=1),
	f("instructions", "Data", "Instructions"), f("dispensed", "Check", "Dispensed", read_only=1)], istable=1)
doctype("Encounter Lab Test", [
	f("service", "Link", "Test", options="Hospital Service", reqd=1, in_list_view=1),
	f("urgent", "Check", "Urgent", in_list_view=1), f("lab_order", "Link", "Lab Order", options="Lab Order", read_only=1, in_list_view=1)], istable=1)
doctype("Encounter Radiology", [
	f("service", "Link", "Exam", options="Hospital Service", reqd=1, in_list_view=1),
	f("body_part", "Data", "Body Part", in_list_view=1), f("clinical_info", "Data", "Clinical Information"),
	f("radiology_order", "Link", "Radiology Order", options="Radiology Order", read_only=1, in_list_view=1)], istable=1)
doctype("Encounter Procedure", [
	f("service", "Link", "Procedure", options="Hospital Service", reqd=1, in_list_view=1),
	f("qty", "Float", "Quantity", default=1, in_list_view=1), f("charge", "Link", "Charge", options="Hospital Charge", read_only=1, in_list_view=1)], istable=1)

doctype("Patient Encounter", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("doctor", "Link", "Doctor", options="Hospital Doctor", reqd=1, in_list_view=1, in_standard_filter=1),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	col("cb1"),
	f("encounter_date", "Datetime", "Date", reqd=1, default="Now", in_list_view=1),
	f("encounter_type", "Select", "Type", options=S("Outpatient", "Inpatient Round", "Emergency", "Telemedicine"), default="Outpatient"),
	f("status", "Select", "Status", options=S("Open", "Completed", "Cancelled"), default="Open", in_list_view=1, in_standard_filter=1),
	f("appointment", "Link", "Appointment", options="Patient Appointment", read_only=1),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	sec("sb_c", "Consultation"),
	f("vitals", "Link", "Vital Signs", options="Vital Signs"),
	f("chief_complaint", "Small Text", "Chief Complaint"),
	f("history", "Text", "History"),
	f("examination", "Text", "Examination"),
	sec("sb_dx", "Diagnosis"),
	f("diagnoses", "Table", "Diagnosis", options="Encounter Diagnosis"),
	f("plan", "Text", "Plan"),
	sec("sb_rx", "Prescription"),
	f("prescriptions", "Table", "Medicines", options="Encounter Prescription"),
	f("safety_notes", "Small Text", "Safety Notes", read_only=1, description="Allergy and duplicate warnings. They are hints: the doctor decides."),
	sec("sb_ord", "Orders"),
	f("lab_tests", "Table", "Laboratory Tests", options="Encounter Lab Test"),
	f("radiology", "Table", "Radiology", options="Encounter Radiology"),
	f("procedures", "Table", "Procedures", options="Encounter Procedure"),
	sec("sb_f", "Follow-up"),
	f("followup_date", "Date", "Follow-up Date"),
	f("sick_leave_days", "Int", "Sick Leave (days)"),
	f("referral_notes", "Small Text", "Referral / Advice"),
	f("completed_on", "Datetime", "Completed On", read_only=1),
], autoname="format:ENC-.YYYY.-.#####", title_field="patient_name", icon="fa fa-file-text-o", perms=perms((MGR, "all"), (DOC, "all"), (NUR, "rwc"), (REC, "r"), (LAB, "r"),
	(RAD, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")), track_changes=1)

# ================================================================== inpatient
doctype("Bed Stay", [
	f("bed", "Link", "Bed", options="Hospital Bed", reqd=1, in_list_view=1),
	f("from_time", "Datetime", "From", reqd=1, in_list_view=1), f("to_time", "Datetime", "To", in_list_view=1),
	f("daily_rate", "Currency", "Daily Rate", read_only=1, in_list_view=1)], istable=1)
doctype("Admission Deposit", [
	f("posting_date", "Date", "Date", reqd=1, in_list_view=1), f("amount", "Currency", "Amount", reqd=1, in_list_view=1),
	f("mode_of_payment", "Link", "Mode of Payment", options="Mode of Payment", in_list_view=1),
	f("payment_entry", "Link", "Payment Entry", options="Payment Entry", read_only=1, in_list_view=1)], istable=1)

doctype("Inpatient Admission", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("admitting_doctor", "Link", "Admitting Doctor", options="Hospital Doctor", reqd=1),
	f("department", "Link", "Department", options="Hospital Department"),
	col("cb1"),
	f("admission_type", "Select", "Type", options=S("Elective", "Emergency", "Transfer", "Day Case", "Maternity"), default="Elective"),
	f("admitted_on", "Datetime", "Admitted On", reqd=1, default="Now", in_list_view=1),
	f("status", "Select", "Status", options=S("Admitted", "Discharged", "Cancelled"), default="Admitted", in_list_view=1, in_standard_filter=1),
	f("bed", "Link", "Current Bed", options="Hospital Bed", reqd=1, in_list_view=1),
	f("ward", "Link", "Ward", options="Ward", read_only=1, fetch_from="bed.ward"),
	f("emergency_visit", "Link", "From Emergency Visit", options="Emergency Visit", read_only=1),
	sec("sb_c", "Clinical"),
	f("diagnosis", "Small Text", "Admission Diagnosis"),
	f("expected_discharge", "Date", "Expected Discharge"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	f("approval", "Link", "Insurance Approval", options="Insurance Approval"),
	sec("sb_b", "Beds and Charges"),
	f("stays", "Table", "Bed History", options="Bed Stay"),
	f("charged_days", "Int", "Bed-days Posted", read_only=1, default=0),
	sec("sb_d", "Deposits"),
	f("deposits", "Table", "Deposits", options="Admission Deposit"),
	f("deposit_total", "Currency", "Deposits Received", read_only=1),
	sec("sb_dc", "Discharge"),
	f("discharged_on", "Datetime", "Discharged On", read_only=1),
	f("discharge_type", "Select", "Discharge Type", options=S("", "Recovered", "Improved", "Referred", "Against Medical Advice", "Deceased")),
	f("discharge_summary", "Text Editor", "Discharge Summary"),
], autoname="format:ADM-.YYYY.-.#####", title_field="patient_name", icon="fa fa-hospital-o", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "rwc"), (LAB, "r"), (RAD, "r"),
	(PHM, "r"), (CSH, "rw"), (INS, "r")), track_changes=1)

doctype("Nursing Note", [
	f("admission", "Link", "Admission", options="Inpatient Admission", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient", "Link", "Patient", options="Hospital Patient", read_only=1, fetch_from="admission.patient", in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch", read_only=1, fetch_from="admission.branch"),
	f("note_type", "Select", "Type", options=S("Nursing", "Doctor Round", "Handover", "Order"), default="Nursing", in_list_view=1),
	f("recorded_at", "Datetime", "Time", default="Now", reqd=1, in_list_view=1),
	f("note", "Text", "Note", reqd=1),
	f("vitals", "Link", "Vital Signs", options="Vital Signs"),
	f("author", "Link", "By", options="User", read_only=1),
], autoname="format:NTE-.YYYY.-.######", icon="fa fa-pencil-square-o", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "r"), (INS, "r")))

doctype("Medication Administration", [
	f("admission", "Link", "Admission", options="Inpatient Admission", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient", "Link", "Patient", options="Hospital Patient", read_only=1, fetch_from="admission.patient", in_list_view=1),
	f("branch", "Link", "Branch", options="Hospital Branch", read_only=1, fetch_from="admission.branch"),
	f("item_code", "Link", "Medicine", options="Item", reqd=1, in_list_view=1),
	f("dose", "Data", "Dose", in_list_view=1), f("route", "Select", "Route", options=S("", "Oral", "IV", "IM", "SC", "Inhaled", "Topical", "Rectal", "Other")),
	col("cb1"),
	f("scheduled_at", "Datetime", "Scheduled At", reqd=1, in_list_view=1),
	f("status", "Select", "Status", options=S("Scheduled", "Given", "Held", "Refused", "Missed"), default="Scheduled", in_list_view=1, in_standard_filter=1),
	f("given_at", "Datetime", "Given At", read_only=1),
	f("given_by", "Link", "Given By", options="User", read_only=1),
	f("notes", "Small Text", "Notes"),
], autoname="format:MAR-.YYYY.-.######", title_field="item_code", icon="fa fa-medkit", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (PHM, "r")))

# ================================================================== laboratory
doctype("Lab Test Parameter", [
	f("parameter", "Data", "Parameter", reqd=1, in_list_view=1), f("unit", "Data", "Unit", in_list_view=1),
	f("result_type", "Select", "Result Type", options=S("Numeric", "Text", "Select"), default="Numeric", in_list_view=1),
	f("select_options", "Small Text", "Choices (one per line)")], istable=1)
doctype("Lab Reference Range", [
	f("parameter", "Data", "Parameter", reqd=1, in_list_view=1),
	f("gender", "Select", "Gender", options=S("Any", "Male", "Female"), default="Any", in_list_view=1),
	f("age_from", "Float", "Age From (years)"), f("age_to", "Float", "Age To (years)"),
	f("low", "Float", "Low", in_list_view=1), f("high", "Float", "High", in_list_view=1),
	f("crit_low", "Float", "Critical Below"), f("crit_high", "Float", "Critical Above"), f("text_range", "Data", "Printed Range")], istable=1)
doctype("Lab Test Template", [
	f("service", "Link", "Service", options="Hospital Service", reqd=1, unique=1, in_list_view=1),
	f("template_name", "Data", "Test", read_only=1, fetch_from="service.service_name", in_list_view=1),
	f("sample_type", "Select", "Sample", options=S("", "Blood", "Serum", "Plasma", "Urine", "Stool", "Swab", "Sputum", "CSF", "Tissue", "Other")),
	f("container", "Data", "Container"),
	f("tat_hours", "Int", "Turnaround (hours)", default=24),
	sec("sb_p", "Parameters"),
	f("parameters", "Table", "Parameters", options="Lab Test Parameter"),
	f("ranges", "Table", "Reference Ranges", options="Lab Reference Range", description="Per parameter, gender and age. The most specific range that fits the patient is used."),
], autoname="field:service", title_field="template_name", icon="fa fa-flask", perms=perms((MGR, "all"), (LAB, "all"), (DOC, "r"), (NUR, "r")))

doctype("Lab Order Test", [
	f("service", "Link", "Test", options="Hospital Service", reqd=1, in_list_view=1),
	f("status", "Select", "Status", options=S("Ordered", "Sample Collected", "Resulted", "Verified", "Cancelled"), default="Ordered", read_only=1, in_list_view=1),
	f("sample_id", "Data", "Sample ID", in_list_view=1),
	f("collected_on", "Datetime", "Collected On", read_only=1),
	f("result", "Link", "Result", options="Lab Result", read_only=1, in_list_view=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1)], istable=1)

doctype("Lab Order", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("ordering_doctor", "Link", "Ordering Doctor", options="Hospital Doctor"),
	col("cb1"),
	f("ordered_on", "Datetime", "Ordered On", default="Now", reqd=1, in_list_view=1),
	f("priority", "Select", "Priority", options=S("Routine", "Urgent", "STAT"), default="Routine", in_list_view=1, in_standard_filter=1),
	f("status", "Select", "Status", options=S("Ordered", "In Progress", "Completed", "Cancelled"), default="Ordered", read_only=1, in_list_view=1, in_standard_filter=1),
	f("encounter", "Link", "Encounter", options="Patient Encounter"),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("emergency_visit", "Link", "Emergency Visit", options="Emergency Visit"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	sec("sb_t", "Tests"),
	f("tests", "Table", "Tests", options="Lab Order Test"),
	f("clinical_info", "Small Text", "Clinical Information"),
	f("has_critical", "Check", "Has a Critical Result", read_only=1),
], autoname="format:LAB-.YYYY.-.#####", title_field="patient_name", icon="fa fa-flask", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "rwc"), (LAB, "all"), (CSH, "r"), (INS, "r")), track_changes=1)

doctype("Lab Result Value", [
	f("parameter", "Data", "Parameter", read_only=1, in_list_view=1),
	f("value", "Data", "Result", in_list_view=1), f("unit", "Data", "Unit", read_only=1, in_list_view=1),
	f("reference", "Data", "Reference", read_only=1, in_list_view=1),
	f("flag", "Data", "Flag", read_only=1, in_list_view=1),
	f("result_type", "Data", "Type", read_only=1, hidden=1)], istable=1)

doctype("Lab Result", [
	f("lab_order", "Link", "Lab Order", options="Lab Order", reqd=1, read_only=1, in_list_view=1, in_standard_filter=1),
	f("patient", "Link", "Patient", options="Hospital Patient", read_only=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", read_only=1, in_standard_filter=1),
	col("cb1"),
	f("service", "Link", "Test", options="Hospital Service", read_only=1, in_list_view=1),
	f("status", "Select", "Status", options=S("Draft", "Resulted", "Verified"), default="Draft", in_list_view=1, in_standard_filter=1),
	f("sample_id", "Data", "Sample ID", read_only=1),
	f("has_critical", "Check", "Critical", read_only=1, in_list_view=1),
	sec("sb_v", "Results"),
	f("result_values", "Table", "Results", options="Lab Result Value"),
	f("comments", "Small Text", "Comments"),
	sec("sb_s", "Sign-off"),
	f("resulted_on", "Datetime", "Resulted On", read_only=1),
	f("resulted_by", "Link", "Resulted By", options="User", read_only=1),
	f("verified_on", "Datetime", "Verified On", read_only=1),
	f("verified_by", "Link", "Verified By", options="User", read_only=1),
], autoname="format:LRS-.YYYY.-.#####", title_field="patient_name", icon="fa fa-file-text", perms=perms((MGR, "all"), (LAB, "all"), (DOC, "r"), (NUR, "r"), (REC, "r")), track_changes=1)

# ================================================================== radiology
doctype("Radiology Order", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("ordering_doctor", "Link", "Ordering Doctor", options="Hospital Doctor"),
	col("cb1"),
	f("service", "Link", "Exam", options="Hospital Service", reqd=1, in_list_view=1),
	f("modality", "Select", "Modality", options=S("X-Ray", "CT", "MRI", "Ultrasound", "Mammography", "Fluoroscopy", "Echo", "ECG", "Other"), default="X-Ray", in_list_view=1, in_standard_filter=1),
	f("body_part", "Data", "Body Part"),
	f("priority", "Select", "Priority", options=S("Routine", "Urgent", "STAT"), default="Routine", in_standard_filter=1),
	f("status", "Select", "Status", options=S("Ordered", "Scheduled", "Performed", "Reported", "Verified", "Cancelled"), default="Ordered", in_list_view=1, in_standard_filter=1),
	f("ordered_on", "Datetime", "Ordered On", default="Now", reqd=1),
	sec("sb_c", "Request"),
	f("clinical_info", "Small Text", "Clinical Information"),
	f("contrast", "Check", "With Contrast"),
	f("encounter", "Link", "Encounter", options="Patient Encounter"),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("emergency_visit", "Link", "Emergency Visit", options="Emergency Visit"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	sec("sb_e", "Examination"),
	f("scheduled_at", "Datetime", "Scheduled At"),
	f("performed_on", "Datetime", "Performed On", read_only=1),
	f("technician", "Data", "Technician"),
	f("images", "Attach", "Images / Study"),
	sec("sb_r", "Report"),
	f("radiologist", "Link", "Radiologist", options="Hospital Doctor"),
	f("findings", "Text", "Findings"),
	f("impression", "Text Editor", "Impression"),
	f("critical", "Check", "Critical Finding"),
	f("verified_on", "Datetime", "Verified On", read_only=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1),
], autoname="format:RAD-.YYYY.-.#####", title_field="patient_name", icon="fa fa-eye", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "rwc"), (RAD, "all"), (CSH, "r"), (INS, "r")), track_changes=1)

# ================================================================== surgery
doctype("Preop Check", [
	f("check_item", "Data", "Check", reqd=1, in_list_view=1), f("done", "Check", "Done", in_list_view=1),
	f("done_by", "Link", "By", options="User", read_only=1), f("done_on", "Datetime", "On", read_only=1)], istable=1)
doctype("Surgery Team", [
	f("doctor", "Link", "Doctor", options="Hospital Doctor", reqd=1, in_list_view=1),
	f("role", "Select", "Role", options=S("Assistant Surgeon", "Anesthetist", "Scrub Nurse", "Other"), default="Assistant Surgeon", in_list_view=1),
	f("service", "Link", "Fee Service", options="Hospital Service", description="Charged when the surgery is completed.", in_list_view=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1)], istable=1)
doctype("Surgery Consumable", [
	f("item_code", "Link", "Item", options="Item", reqd=1, in_list_view=1), f("item_name", "Data", "Name", read_only=1),
	f("qty", "Float", "Quantity", reqd=1, default=1, in_list_view=1),
	f("batches", "Small Text", "Batches", read_only=1), f("rate", "Currency", "Price", read_only=1, in_list_view=1), f("amount", "Currency", "Amount", read_only=1, in_list_view=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1)], istable=1)

doctype("Surgery Booking", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("service", "Link", "Procedure", options="Hospital Service", reqd=1, in_list_view=1),
	col("cb1"),
	f("surgeon", "Link", "Surgeon", options="Hospital Doctor", reqd=1, in_list_view=1, in_standard_filter=1),
	f("operating_room", "Link", "Operating Room", options="Operating Room", reqd=1, in_standard_filter=1),
	f("anesthesia_type", "Select", "Anesthesia", options=S("General", "Spinal", "Epidural", "Local", "Sedation", "None"), default="General"),
	f("status", "Select", "Status", options=S("Booked", "Pre-op Ready", "In Progress", "Completed", "Cancelled"), default="Booked", in_list_view=1, in_standard_filter=1),
	sec("sb_t", "Time"),
	f("scheduled_start", "Datetime", "Scheduled Start", reqd=1, in_list_view=1),
	f("expected_minutes", "Int", "Expected Duration (minutes)", reqd=1, default=60),
	f("scheduled_end", "Datetime", "Scheduled End", read_only=1),
	col("cb2"),
	f("actual_start", "Datetime", "Actual Start", read_only=1),
	f("actual_end", "Datetime", "Actual End", read_only=1),
	sec("sb_team", "Team"),
	f("team", "Table", "Team", options="Surgery Team"),
	sec("sb_pre", "Pre-operative Checklist"),
	f("preop", "Table", "Checklist", options="Preop Check"),
	sec("sb_c", "Consumables"),
	f("consumables", "Table", "Consumables", options="Surgery Consumable", description="Issued from the operating theatre warehouse when the surgery is completed."),
	f("stock_entry", "Link", "Stock Entry", options="Stock Entry", read_only=1),
	sec("sb_n", "Operation Notes"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	f("approval", "Link", "Insurance Approval", options="Insurance Approval"),
	f("operation_notes", "Text Editor", "Operation Notes"),
	f("complications", "Small Text", "Complications"),
	f("procedure_charge", "Link", "Procedure Charge", options="Hospital Charge", read_only=1),
	f("theatre_charge", "Link", "Theatre Time Charge", options="Hospital Charge", read_only=1),
], autoname="format:SUR-.YYYY.-.#####", title_field="patient_name", icon="fa fa-scissors", perms=perms((MGR, "all"), (DOC, "all"), (NUR, "rwc"), (REC, "r"), (PHM, "r"), (CSH, "r"), (INS, "r")), track_changes=1)

# ================================================================== emergency
doctype("Emergency Visit", [
	f("patient", "Link", "Patient", options="Hospital Patient", in_list_view=1, in_standard_filter=1, description="Leave empty for an unidentified patient and register later."),
	f("unidentified", "Check", "Unidentified Patient"),
	f("temp_name", "Data", "Temporary Name", depends_on="unidentified"),
	f("temp_gender", "Select", "Gender", options=S("", "Male", "Female"), depends_on="unidentified"),
	f("approx_age", "Int", "Approximate Age (years)", depends_on="unidentified"),
	col("cb1"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("arrival_time", "Datetime", "Arrival", default="Now", reqd=1, in_list_view=1),
	f("arrival_mode", "Select", "Arrived By", options=S("Walk-in", "Ambulance", "Referral", "Police", "Other"), default="Walk-in"),
	f("ambulance", "Data", "Ambulance / Vehicle"),
	sec("sb_t", "Triage"),
	f("complaint", "Small Text", "Complaint", reqd=1),
	f("triage_level", "Select", "Triage Level (1 = most urgent)", options=S("", "1", "2", "3", "4", "5"), in_list_view=1, in_standard_filter=1),
	f("triage_color", "Data", "Color", read_only=1),
	f("vitals", "Link", "Vital Signs", options="Vital Signs"),
	f("triaged_by", "Link", "Triaged By", options="User", read_only=1),
	col("cb2"),
	f("status", "Select", "Status", options=S("Waiting", "In Treatment", "Observation", "Admitted", "Discharged", "Transferred", "Deceased", "Left Without Being Seen"), default="Waiting",
		in_list_view=1, in_standard_filter=1),
	f("assigned_doctor", "Link", "Doctor", options="Hospital Doctor"),
	f("seen_at", "Datetime", "Seen By Doctor At", read_only=1),
	f("wait_minutes", "Int", "Wait Until Seen (minutes)", read_only=1),
	sec("sb_c", "Care"),
	f("service", "Link", "Emergency Service", options="Hospital Service", description="Charged when the visit is registered (or when the patient is linked to it). Empty = nothing is charged automatically."),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	f("notes", "Text", "Notes"),
	sec("sb_d", "Disposition"),
	f("disposition_time", "Datetime", "Closed At", read_only=1),
	f("admission", "Link", "Admission", options="Inpatient Admission", read_only=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1),
], autoname="format:ER-.YYYY.-.#####", title_field="complaint", icon="fa fa-ambulance", perms=perms((MGR, "all"), (DOC, "rwc"), (NUR, "rwc"), (REC, "rwc"), (CSH, "r"), (INS, "r")), track_changes=1)

# ================================================================== pharmacy
doctype("Dispense Line", [
	f("item_code", "Link", "Medicine", options="Item", reqd=1, in_list_view=1),
	f("item_name", "Data", "Name", read_only=1, in_list_view=1),
	f("qty", "Float", "Quantity", reqd=1, default=1, in_list_view=1),
	f("uom", "Link", "Unit", options="UOM", read_only=1),
	f("rate", "Currency", "Price", in_list_view=1), f("amount", "Currency", "Amount", read_only=1, in_list_view=1),
	f("batches", "Small Text", "Batches", read_only=1),
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1),
	f("prescription_row", "Data", "Prescription Row", hidden=1)], istable=1)

doctype("Medication Dispense", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("posting_date", "Date", "Date", default="Today", reqd=1, in_list_view=1),
	col("cb1"),
	f("encounter", "Link", "Encounter", options="Patient Encounter"),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("doctor", "Link", "Prescriber", options="Hospital Doctor"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	f("is_return", "Check", "Return", in_list_view=1),
	f("return_against", "Link", "Return Against", options="Medication Dispense", depends_on="is_return"),
	sec("sb_l", "Medicines"),
	f("items", "Table", "Medicines", options="Dispense Line", reqd=1),
	f("total", "Currency", "Total", read_only=1, in_list_view=1),
	f("safety_notes", "Small Text", "Safety Notes", read_only=1),
	f("warehouse", "Link", "Warehouse", options="Warehouse", read_only=1),
	f("stock_entry", "Link", "Stock Entry", options="Stock Entry", read_only=1),
	f("amended_from", "Link", "Amended From", options="Medication Dispense", read_only=1, no_copy=1, print_hide=1),
], autoname="format:DSP-.YYYY.-.#####", title_field="patient_name", is_submittable=1, icon="fa fa-medkit",
	perms=perms((MGR, "full"), (PHM, "full"), (DOC, "r"), (NUR, "rwc"), (CSH, "r"), (INS, "r")), track_changes=1)

# ================================================================== billing and money
doctype("Hospital Charge", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("posting_date", "Date", "Date", default="Today", reqd=1, in_list_view=1),
	f("status", "Select", "Status", options=S("Unbilled", "Billed", "Cancelled"), default="Unbilled", in_list_view=1, in_standard_filter=1),
	col("cb1"),
	f("service", "Link", "Service", options="Hospital Service", in_list_view=1),
	f("item_code", "Link", "Item", options="Item", in_list_view=1, description="Set automatically from the service. Medicines use their own item."),
	f("description", "Data", "Description"),
	f("service_type", "Select", "Type", options="\n" + SERVICE_TYPES, in_standard_filter=1),
	f("department", "Link", "Department", options="Hospital Department"),
	f("doctor", "Link", "Performing Doctor", options="Hospital Doctor", in_standard_filter=1),
	sec("sb_a", "Amount"),
	f("qty", "Float", "Quantity", default=1, reqd=1, in_list_view=1),
	f("rate", "Currency", "Price", in_list_view=1),
	f("discount_pct", "Percent", "Discount %"),
	f("amount", "Currency", "Amount", read_only=1, in_list_view=1),
	sec("sb_s", "Source"),
	f("admission", "Link", "Admission", options="Inpatient Admission"),
	f("encounter", "Link", "Encounter", options="Patient Encounter"),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan"),
	f("approved", "Check", "Prior Approval Obtained"),
	col("cb2"),
	f("source_doctype", "Data", "Source Type", read_only=1),
	f("source_name", "Data", "Source", read_only=1),
	f("bill", "Link", "Bill", options="Hospital Bill", read_only=1),
], autoname="format:CHG-.YYYY.-.######", title_field="description", icon="fa fa-money", perms=perms((MGR, "all"), (CSH, "rwc"), (DOC, "r"), (NUR, "rwc"), (REC, "rwc"), (LAB, "r"), (RAD, "r"), (PHM, "r"), (INS, "r")), track_changes=1)

doctype("Bill Line", [
	f("charge", "Link", "Charge", options="Hospital Charge", read_only=1, in_list_view=1),
	f("item_code", "Link", "Item", options="Item", read_only=1),
	f("description", "Data", "Description", read_only=1, in_list_view=1),
	f("service", "Link", "Service", options="Hospital Service", read_only=1),
	f("service_type", "Data", "Type", read_only=1),
	f("doctor", "Link", "Doctor", options="Hospital Doctor", read_only=1),
	f("qty", "Float", "Qty", read_only=1, in_list_view=1), f("rate", "Currency", "Price", read_only=1, in_list_view=1),
	f("amount", "Currency", "Amount", read_only=1, in_list_view=1),
	f("insurer_share", "Currency", "Insurer", read_only=1, in_list_view=1), f("patient_share", "Currency", "Patient", read_only=1, in_list_view=1),
	f("reason", "Data", "Note", read_only=1),
	f("doctor_share", "Currency", "Doctor's Share", read_only=1),
	f("statement", "Link", "Doctor Statement", options="Doctor Statement", read_only=1)], istable=1)

doctype("Hospital Bill", [
	f("patient", "Link", "Patient", options="Hospital Patient", reqd=1, in_list_view=1, in_standard_filter=1),
	f("patient_name", "Data", "Patient Name", read_only=1, fetch_from="patient.patient_name"),
	f("branch", "Link", "Branch", options="Hospital Branch", reqd=1, in_standard_filter=1),
	f("company", "Link", "Company", options="Company", read_only=1, fetch_from="branch.company"),
	f("posting_date", "Date", "Date", default="Today", reqd=1, in_list_view=1),
	col("cb1"),
	f("admission", "Link", "Admission", options="Inpatient Admission", description="Fill to bill one stay. Empty = every unbilled charge of the patient."),
	f("insurance_plan", "Link", "Insurance Plan", options="Hospital Insurance Plan", in_standard_filter=1),
	f("member_no", "Data", "Member No."),
	f("status", "Select", "Status", options=S("Draft", "Unpaid", "Partly Paid", "Paid", "Credit", "Cancelled"), default="Draft", read_only=1, in_list_view=1, in_standard_filter=1),
	sec("sb_l", "Lines"),
	f("lines", "Table", "Lines", options="Bill Line", reqd=1),
	sec("sb_t", "Totals"),
	f("gross_total", "Currency", "Total", read_only=1, in_list_view=1),
	f("insurer_total", "Currency", "Insurer Pays", read_only=1),
	f("patient_total", "Currency", "Patient Pays", read_only=1, in_list_view=1),
	col("cb2"),
	f("annual_remaining", "Currency", "Member's Annual Limit Left", read_only=1),
	f("deposits_applied", "Currency", "Advances Applied", read_only=1),
	f("patient_outstanding", "Currency", "Patient Balance", read_only=1),
	sec("sb_d", "Documents"),
	f("patient_invoice", "Link", "Patient Invoice", options="Sales Invoice", read_only=1),
	f("insurer_invoice", "Link", "Insurer Invoice", options="Sales Invoice", read_only=1),
	f("claim", "Link", "Claim", options="Insurance Claim", read_only=1),
	f("amended_from", "Link", "Amended From", options="Hospital Bill", read_only=1, no_copy=1, print_hide=1),
], autoname="format:BIL-.YYYY.-.#####", title_field="patient_name", is_submittable=1, icon="fa fa-file-text-o",
	perms=perms((MGR, "full"), (CSH, "full"), (INS, "rw"), (DOC, "r"), (NUR, "r"), (REC, "rwc")), track_changes=1)

doctype("Claim Line", [
	f("bill", "Link", "Bill", options="Hospital Bill", reqd=1, in_list_view=1),
	f("patient", "Link", "Patient", options="Hospital Patient", read_only=1, in_list_view=1),
	f("posting_date", "Date", "Date", read_only=1),
	f("invoice", "Link", "Invoice", options="Sales Invoice", read_only=1, in_list_view=1),
	f("amount", "Currency", "Claimed", read_only=1, in_list_view=1),
	f("rejected_amount", "Currency", "Rejected", in_list_view=1),
	f("paid_amount", "Currency", "Paid", read_only=1, in_list_view=1),
	f("rejection_reason", "Data", "Reason"),
	f("writeoff_entry", "Link", "Write-off Entry", options="Journal Entry", read_only=1)], istable=1)

doctype("Insurance Claim", [
	f("insurance_company", "Link", "Insurance Company", options="Hospital Insurer", reqd=1, in_list_view=1, in_standard_filter=1),
	f("branch", "Link", "Branch", options="Hospital Branch", in_standard_filter=1),
	f("from_date", "Date", "From", reqd=1), f("to_date", "Date", "To", reqd=1),
	col("cb1"),
	f("status", "Select", "Status", options=S("Draft", "Submitted", "Partially Paid", "Paid", "Rejected"), default="Draft", read_only=1, in_list_view=1, in_standard_filter=1),
	f("submitted_on", "Date", "Submitted On", read_only=1),
	f("due_date", "Date", "Payment Due", read_only=1),
	sec("sb_l", "Bills"),
	f("lines", "Table", "Bills", options="Claim Line"),
	sec("sb_t", "Totals"),
	f("total_amount", "Currency", "Claimed", read_only=1, in_list_view=1),
	f("rejected_total", "Currency", "Rejected", read_only=1),
	f("paid_total", "Currency", "Paid", read_only=1),
	f("outstanding", "Currency", "Outstanding", read_only=1, in_list_view=1),
	f("notes", "Small Text", "Notes"),
], autoname="format:CLM-.YYYY.-.#####", title_field="insurance_company", icon="fa fa-folder-open", perms=perms((MGR, "all"), (INS, "all"), (CSH, "rw")), track_changes=1)

doctype("Statement Row", [
	f("bill", "Link", "Bill", options="Hospital Bill", read_only=1, in_list_view=1),
	f("posting_date", "Date", "Date", read_only=1, in_list_view=1),
	f("patient", "Link", "Patient", options="Hospital Patient", read_only=1, in_list_view=1),
	f("description", "Data", "Service", read_only=1, in_list_view=1),
	f("amount", "Currency", "Amount", read_only=1, in_list_view=1), f("share", "Currency", "Doctor's Share", read_only=1, in_list_view=1),
	f("bill_line", "Data", "Bill Line", read_only=1, hidden=1)], istable=1)

doctype("Doctor Statement", [
	f("doctor", "Link", "Doctor", options="Hospital Doctor", reqd=1, in_list_view=1, in_standard_filter=1),
	f("branch", "Link", "Branch", options="Hospital Branch", description="Empty = every branch."),
	f("company", "Link", "Company", options="Company", reqd=1),
	f("from_date", "Date", "From", reqd=1), f("to_date", "Date", "To", reqd=1),
	col("cb1"),
	f("status", "Select", "Status", options=S("Draft", "Approved", "Paid", "Cancelled"), default="Draft", read_only=1, in_list_view=1, in_standard_filter=1),
	f("posting_date", "Date", "Date", default="Today"),
	sec("sb_r", "Rows"),
	f("rows", "Table", "Rows", options="Statement Row"),
	sec("sb_t", "Totals"),
	f("gross_total", "Currency", "Billed", read_only=1),
	f("share_total", "Currency", "Doctor's Share", read_only=1),
	f("deductions", "Currency", "Deductions"),
	f("deduction_note", "Data", "Deduction Reason"),
	f("net_payable", "Currency", "Net Payable", read_only=1, in_list_view=1),
	f("purchase_invoice", "Link", "Purchase Invoice", options="Purchase Invoice", read_only=1),
], autoname="format:DST-.YYYY.-.#####", title_field="doctor", icon="fa fa-user-md", perms=perms((MGR, "all"), (CSH, "rw"), (DOC, "r")), track_changes=1)


def build():
	os.makedirs(ROOT, exist_ok=True)
	for name, d in DT.items():
		fields = d["fields"]
		order = [x["fieldname"] for x in fields]
		istable = d.get("istable", 0)
		out = {
			"actions": [], "creation": TS, "doctype": "DocType", "engine": "InnoDB", "field_order": order, "fields": fields,
			"links": [], "modified": TS, "modified_by": "Administrator", "module": MODULE, "name": name, "owner": "Administrator",
			"sort_field": "creation", "sort_order": "DESC", "states": [],
			"permissions": [] if istable else d.get("perms", []),
		}
		for k in ("autoname", "title_field", "icon", "track_changes", "issingle", "istable", "show_title_field_in_link", "search_fields", "is_submittable"):
			if k in d:
				out[k] = d[k]
		if istable:
			out["editable_grid"] = 1
		if "autoname" not in d and not istable and not d.get("issingle"):
			out["autoname"] = "hash"
		out["allow_rename"] = 0
		slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
		folder = os.path.join(ROOT, slug)
		os.makedirs(folder, exist_ok=True)
		open(os.path.join(folder, "__init__.py"), "a").close()
		with open(os.path.join(folder, slug + ".json"), "w", encoding="utf-8") as fh:
			json.dump(out, fh, indent=1, ensure_ascii=False)
			fh.write("\n")
		py = os.path.join(folder, slug + ".py")
		if not os.path.exists(py):
			cls = "".join(w.capitalize() for w in re.split(r"[^A-Za-z0-9]+", name))
			with open(py, "w") as fh:
				fh.write(f"from frappe.model.document import Document\n\n\nclass {cls}(Document):\n\tpass\n")


if __name__ == "__main__":
	build()
	print(len(DT), "doctypes")
