"""Demo data for the Hospital app: branches, wards, doctors, services, insurers, medicines with batches, patients and a few
end-to-end stories (insured outpatient, cash paediatric visit, an inpatient stay billed to an insurer, a Saudi branch visit).

    bench --site mysite.localhost execute ledgerx_hospital.demo.run

Run ledgerx.demo.foundation first (companies, cost centers, warehouses). Take a backup first.
Idempotent: every record is looked up by its natural key before it is created, so running again adds only what is missing.
Every step commits on its own and reports its result; failures are logged in Error Log under titles starting 'Demo hospital'.
Run as Administrator (bench execute does): charges are made through the app's own charges.add_charge and bills through billing.
"""
import frappe
from frappe.utils import add_days, add_months, add_to_date, flt, getdate, now_datetime, nowdate

from ledgerx.shared import run_each
from ledgerx_hospital import billing, charges

EGYPT, SAUDI = "LedgerX Egypt", "LedgerX Saudi"
PL_EGP, PL_SAR = "Hospital Cash EGP", "Hospital Cash SAR"
MEDICINE_GROUP = "Hospital Medicines"
PRICE_LIST_CURRENCY = {PL_EGP: "EGP", PL_SAR: "SAR"}

DEPARTMENTS = [("General Medicine", "Clinical"), ("Cardiology", "Clinical"), ("Pediatrics", "Clinical"), ("Laboratory", "Support"), ("Radiology", "Support"),
	("Inpatient Ward", "Clinical"), ("Pharmacy", "Support"), ("Administration", "Administrative")]
SPECIALTIES = ["General Practice", "Internal Medicine", "Pediatrics", "Cardiology", "Radiology"]

# code, name, type, department, EGP price, SAR price
SERVICES = [
	("CONS-IM", "Internal Medicine Consultation", "Consultation", "General Medicine", 400, 250),
	("CONS-CARD", "Cardiology Consultation", "Consultation", "Cardiology", 600, 350),
	("CONS-PED", "Pediatrics Consultation", "Consultation", "Pediatrics", 350, 220),
	("CONS-GP", "General Practice Consultation", "Consultation", "General Medicine", 250, 150),
	("LAB-CBC", "Complete Blood Count", "Laboratory", "Laboratory", 180, 60),
	("LAB-GLU", "Fasting Blood Glucose", "Laboratory", "Laboratory", 90, 30),
	("LAB-HBA1C", "HbA1c", "Laboratory", "Laboratory", 280, 90),
	("LAB-LIPID", "Lipid Profile", "Laboratory", "Laboratory", 380, 120),
	("LAB-CRP", "C-Reactive Protein", "Laboratory", "Laboratory", 250, 80),
	("RAD-XR-CHEST", "Chest X-Ray", "Radiology", "Radiology", 300, 120),
	("RAD-US-ABD", "Abdominal Ultrasound", "Radiology", "Radiology", 450, 200),
	("RAD-CT-CHEST", "CT Chest", "Radiology", "Radiology", 2800, 900),
	("RAD-ECG", "Resting ECG", "Radiology", "Radiology", 200, 80),
	("PRC-NEB", "Nebulization Session", "Procedure", "Pediatrics", 150, 60),
	("PRC-DRESS", "Wound Dressing", "Procedure", "General Medicine", 120, 50),
	("PRC-IVINF", "IV Infusion Administration", "Procedure", "Inpatient Ward", 200, 80),
	("ROOM-STD", "Standard Ward Bed - Day", "Room", "Inpatient Ward", 1200, 450),
	("ROOM-PVT", "Private Room - Day", "Room", "Inpatient Ward", 2800, 900),
	("ROOM-ICU", "ICU Bed - Day", "Room", "Inpatient Ward", 7500, 2500),
]
MODALITY = {"RAD-XR-CHEST": "X-Ray", "RAD-US-ABD": "Ultrasound", "RAD-CT-CHEST": "CT", "RAD-ECG": "ECG"}

# service -> (sample type, [(parameter, unit)], [(parameter, gender, low, high, crit_low, crit_high)])
LAB_TEMPLATES = {
	"LAB-CBC": ("Blood", [("Hemoglobin", "g/dL"), ("WBC", "x10^3/uL"), ("Platelets", "x10^3/uL")],
		[("Hemoglobin", "Male", 13.0, 17.0, 7.0, 20.0), ("Hemoglobin", "Female", 12.0, 15.5, 7.0, 20.0), ("WBC", "Any", 4.0, 11.0, 2.0, 30.0), ("Platelets", "Any", 150, 450, 50, 1000)]),
	"LAB-GLU": ("Serum", [("Fasting Glucose", "mg/dL")], [("Fasting Glucose", "Any", 70, 100, 40, 400)]),
	"LAB-HBA1C": ("Blood", [("HbA1c", "%")], [("HbA1c", "Any", 4.0, 5.6, None, 14.0)]),
	"LAB-LIPID": ("Serum", [("Total Cholesterol", "mg/dL"), ("LDL Cholesterol", "mg/dL"), ("HDL Cholesterol", "mg/dL"), ("Triglycerides", "mg/dL")],
		[("Total Cholesterol", "Any", None, 200, None, None), ("LDL Cholesterol", "Any", None, 100, None, None), ("HDL Cholesterol", "Male", 40, None, None, None),
		("HDL Cholesterol", "Female", 50, None, None, None), ("Triglycerides", "Any", None, 150, None, 1000)]),
	"LAB-CRP": ("Serum", [("CRP", "mg/L")], [("CRP", "Any", None, 5, None, None)]),
}

# name, company, cost center, pharmacy warehouse (created when missing), price list, phone, address
BRANCHES = [
	("Cairo Hospital", EGYPT, "Cairo - LXE", "Cairo Hospital Pharmacy", PL_EGP, "+20 2 2795 4100", "12 Road 9, Maadi, Cairo"),
	("Alexandria Clinic", EGYPT, "Alexandria - LXE", "Alexandria Clinic Pharmacy", PL_EGP, "+20 3 545 2200", "45 Fouad Street, Alexandria"),
	("Riyadh Hospital", SAUDI, "Riyadh - LXS", "Riyadh Hospital Pharmacy", PL_SAR, "+966 11 462 7000", "King Fahd Road, Olaya, Riyadh"),
]
# ward name, branch, type, [(bed no, room, class, service)]
WARDS = [
	("Cairo General Ward", "Cairo Hospital", "General", [("G-101", "101", "Standard", "ROOM-STD"), ("G-102", "101", "Standard", "ROOM-STD"), ("G-103", "102", "Standard", "ROOM-STD")]),
	("Cairo Private Floor", "Cairo Hospital", "Private", [("P-201", "201", "Private", "ROOM-PVT"), ("P-202", "202", "Private", "ROOM-PVT")]),
	("Cairo ICU", "Cairo Hospital", "ICU", [("ICU-1", "301", "ICU", "ROOM-ICU"), ("ICU-2", "302", "ICU", "ROOM-ICU")]),
	("Riyadh Private Ward", "Riyadh Hospital", "Private", [("R-101", "101", "Private", "ROOM-PVT"), ("R-102", "102", "Private", "ROOM-PVT")]),
]

# name, specialty, department, default branch, [(branch, from, to)], consultation service, licence, mobile, fee rules
DOCTORS = [
	("Dr. Khaled Mansour", "Cardiology", "Cardiology", "Cairo Hospital", [("Cairo Hospital", "09:00:00", "13:00:00"), ("Alexandria Clinic", "16:00:00", "19:00:00")], "CONS-CARD", "EG-MED-48213", "+20 100 234 5671"),
	("Dr. Mona Farouk", "Pediatrics", "Pediatrics", "Cairo Hospital", [("Cairo Hospital", "09:00:00", "14:00:00")], "CONS-PED", "EG-MED-51907", "+20 101 345 6782"),
	("Dr. Ahmed Hassan", "Internal Medicine", "General Medicine", "Cairo Hospital", [("Cairo Hospital", "09:00:00", "15:00:00")], "CONS-IM", "EG-MED-39458", "+20 102 456 7893"),
	("Dr. Heba Saleh", "Radiology", "Radiology", "Cairo Hospital", [], None, "EG-MED-60231", "+20 106 567 8904"),
	("Dr. Omar Ibrahim", "General Practice", "General Medicine", "Alexandria Clinic", [("Alexandria Clinic", "10:00:00", "18:00:00")], "CONS-GP", "EG-MED-44876", "+20 111 678 9015"),
	("Dr. Faisal Al-Nasser", "Internal Medicine", "General Medicine", "Riyadh Hospital", [("Riyadh Hospital", "09:00:00", "16:00:00")], "CONS-IM", "SA-SCFHS-17-3021", "+966 50 123 4501"),
	("Dr. Noura Al-Harbi", "Pediatrics", "Pediatrics", "Riyadh Hospital", [("Riyadh Hospital", "09:00:00", "14:00:00")], "CONS-PED", "SA-SCFHS-19-5584", "+966 55 234 5612"),
]
WEEKDAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
FEE_RULES = [("Consultation", 60), ("Procedure", 30), ("Radiology", 25)]

# insurer, claim days
INSURERS = [("Nile Shield Health Insurance", 45), ("Delta Care Insurance", 60), ("Najd Medical Insurance", 30)]
# plan, insurer, cover %, visit copay, patient cap, annual limit, rules [(service, service type, cover %, requires approval, excluded)]
PLANS = [
	("Nile Shield Gold", "Nile Shield Health Insurance", 90, 0, 0, 150000, [("RAD-CT-CHEST", None, 90, 1, 0), (None, "Pharmacy", 70, 0, 0)]),
	("Nile Shield Basic", "Nile Shield Health Insurance", 70, 100, 4000, 50000, [("RAD-CT-CHEST", None, 70, 0, 1)]),
	("Delta Care Corporate", "Delta Care Insurance", 80, 0, 3000, 120000, [(None, "Pharmacy", 60, 0, 0)]),
	("Najd Premium", "Najd Medical Insurance", 90, 30, 0, 250000, []),
]

# code, name, EGP price, SAR price, EGP cost, SAR cost
MEDICINES = [
	("LXH-PARA", "Paracetamol 500 mg Tablets (strip of 10)", 30, 5, 18, 3),
	("LXH-AMOX", "Amoxicillin 500 mg Capsules (strip of 10)", 75, 14, 48, 9),
	("LXH-AUG", "Amoxicillin/Clavulanate 1 g Tablets (strip of 14)", 210, 38, 140, 25),
	("LXH-OMEP", "Omeprazole 20 mg Capsules (strip of 14)", 95, 16, 60, 10),
	("LXH-SALB", "Salbutamol Inhaler 100 mcg (200 doses)", 110, 18, 70, 11),
	("LXH-ATOR", "Atorvastatin 20 mg Tablets (strip of 10)", 140, 24, 90, 15),
	("LXH-ASP", "Aspirin 81 mg Tablets (strip of 30)", 55, 9, 35, 6),
	("LXH-AMLO", "Amlodipine 5 mg Tablets (strip of 10)", 65, 11, 40, 7),
	("LXH-MET", "Metformin 500 mg Tablets (strip of 20)", 50, 9, 30, 5),
	("LXH-NS", "Sodium Chloride 0.9% IV Infusion 500 ml", 40, 7, 24, 4),
]

# key -> patient
PATIENTS = {
	"mahmoud": dict(name="Mahmoud Abdelrahman Saleh", gender="Male", national_id="27803140101237", mobile="+20 100 411 2233", city="Cairo", branch="Cairo Hospital",
		plan="Nile Shield Gold", member_no="NSH-0045217", blood_group="A+", chronic="Hypertension", allergies="", emergency=("Amira Saleh", "+20 100 411 2244", "Wife"), address="25 Street 9, Maadi, Cairo"),
	"youssef": dict(name="Youssef Karim El-Sayed", gender="Male", national_id="31206210207815", mobile="+20 122 533 4411", city="Giza", branch="Cairo Hospital",
		blood_group="O+", chronic="", allergies="House dust mites", emergency=("Karim El-Sayed", "+20 122 533 4411", "Father"), address="8 Mossadak Street, Dokki, Giza"),
	"salma": dict(name="Salma Hossam Eldin", gender="Female", national_id="29211300203429", mobile="+20 109 622 7788", city="Cairo", branch="Cairo Hospital",
		plan="Delta Care Corporate", member_no="DLC-2291-07", blood_group="B+", chronic="", allergies="", emergency=("Hossam Eldin Ali", "+20 109 622 7700", "Father"), address="14 Abbas El-Akkad, Nasr City, Cairo"),
	"fatma": dict(name="Fatma Ibrahim Mostafa", gender="Female", national_id="28509022104563", mobile="+20 111 744 9900", city="Giza", branch="Cairo Hospital",
		plan="Nile Shield Basic", member_no="NSB-1180422", blood_group="AB+", chronic="Hypertension", allergies="Sulfa drugs", emergency=("Mostafa Ibrahim", "+20 111 744 9911", "Husband"), address="3 Pyramids Road, Giza"),
	"ali": dict(name="Ali Nabil Gaber", gender="Male", national_id="26001050109871", mobile="+20 100 855 1020", city="Cairo", branch="Cairo Hospital",
		blood_group="O-", chronic="COPD, Hypertension", allergies="", emergency=("Nabil Gaber", "+20 100 855 1021", "Son"), address="77 El Haram Street, Giza"),
	"nour": dict(name="Nour Ahmed Fathy", gender="Female", national_id="29804180202146", mobile="+20 120 966 3344", city="Alexandria", branch="Alexandria Clinic",
		blood_group="A-", chronic="", allergies="", emergency=("Ahmed Fathy", "+20 120 966 3300", "Father"), address="21 Gamal Abdel Nasser Road, Alexandria"),
	"abdulrahman": dict(name="Abdulrahman Saeed Al-Qahtani", gender="Male", passport_no="P4412093", dob="1971-08-19", mobile="+966 50 312 8841", city="Riyadh", branch="Riyadh Hospital",
		plan="Najd Premium", member_no="NJD-77120934", blood_group="B+", chronic="Type 2 diabetes mellitus", allergies="", emergency=("Saeed Al-Qahtani", "+966 50 312 8800", "Brother"), address="Al Olaya District, Riyadh"),
	"lama": dict(name="Lama Faisal Al-Otaibi", gender="Female", passport_no="P5598120", dob="2018-05-12", mobile="+966 55 477 2010", city="Riyadh", branch="Riyadh Hospital",
		blood_group="A+", chronic="", allergies="Peanuts", emergency=("Faisal Al-Otaibi", "+966 55 477 2010", "Father"), address="Al Malqa District, Riyadh"),
}

# Outpatient stories: each is appointment -> check-in -> encounter -> lab / radiology / dispense -> bill -> payment (-> claim)
VISITS = {
	"mahmoud": dict(
		patient="mahmoud", doctor="Dr. Khaled Mansour", branch="Cairo Hospital", time="10:00:00", day=0, reason="Demo: exertional chest tightness for two weeks",
		approval=("NSG-2026-48213", "RAD-CT-CHEST", 3200),
		complaint="Chest tightness on climbing stairs, relieved by rest, for two weeks.",
		history="48-year-old man, known hypertensive on no regular treatment, smoker (15 pack-years). Father had a heart attack at 55.",
		exam="BP 150/95, pulse 84 regular. Heart sounds normal, chest clear, no leg edema.",
		vitals=dict(sys_bp=150, dia_bp=95, pulse=84, resp_rate=16, spo2=97, temperature=36.8, blood_glucose=112, weight=92, height=174),
		diagnoses=[("I10", "Essential hypertension", "Primary"), ("I20.9", "Angina pectoris, unspecified", "Provisional")],
		plan="Start antihypertensive and statin, aspirin. Lipid profile, CBC, glucose, ECG, chest X-ray and CT chest. Review with results in one week.",
		prescriptions=[("LXH-ASP", "81 mg", "Once daily", 30, 1), ("LXH-ATOR", "20 mg", "Once daily at night", 30, 3), ("LXH-AMLO", "5 mg", "Once daily", 30, 3)],
		labs=["LAB-LIPID", "LAB-CBC", "LAB-GLU"], radiology=[("RAD-ECG", "Chest", "Exertional chest pain"), ("RAD-XR-CHEST", "Chest", "Exertional chest pain"), ("RAD-CT-CHEST", "Chest", "Exclude coronary calcification")],
		procedures=[],
		lab_values={"LAB-LIPID": {"Total Cholesterol": "248", "LDL Cholesterol": "162", "HDL Cholesterol": "38", "Triglycerides": "190"},
			"LAB-CBC": {"Hemoglobin": "14.6", "WBC": "7.8", "Platelets": "254"}, "LAB-GLU": {"Fasting Glucose": "112"}},
		reports={"RAD-ECG": ("Sinus rhythm, rate 82/min. Mild ST depression in V4-V6.", "Non-specific ST-T changes. Correlate clinically."),
			"RAD-XR-CHEST": ("Heart size at the upper limit of normal. Clear lung fields. No effusion.", "No acute chest pathology."),
			"RAD-CT-CHEST": ("Moderate coronary artery calcification. No pulmonary embolism. Lungs clear.", "Coronary calcification: cardiology follow-up advised.")},
		followup=7, followup_reason="Demo: follow-up on tests and treatment", pay=True, claim=0.6),
	"youssef": dict(
		patient="youssef", doctor="Dr. Mona Farouk", branch="Cairo Hospital", time="10:30:00", day=0, reason="Demo: wheeze and night cough",
		complaint="Night cough and wheeze for three days, worse with dust.",
		history="14-year-old with childhood asthma, last attack six months ago. No fever.",
		exam="Mild bilateral wheeze, no distress, good air entry.",
		vitals=dict(pulse=104, resp_rate=26, spo2=95, temperature=37.4, weight=38, height=150),
		diagnoses=[("J45.9", "Asthma, uncomplicated", "Primary")],
		plan="Nebulization in clinic, salbutamol inhaler as needed, avoid dust. Review if no improvement in 3 days.",
		prescriptions=[("LXH-SALB", "2 puffs", "Every 6 hours when needed", 14, 1), ("LXH-PARA", "500 mg", "Every 8 hours if fever", 3, 1)],
		labs=[], radiology=[], procedures=[("PRC-NEB", 1)], lab_values={}, reports={}, pay=True, claim=None),
	"abdulrahman": dict(
		patient="abdulrahman", doctor="Dr. Faisal Al-Nasser", branch="Riyadh Hospital", time="10:00:00", day=0, reason="Demo: diabetes follow-up",
		complaint="Routine diabetes follow-up; occasional morning dizziness.",
		history="54-year-old with type 2 diabetes for nine years on metformin. Diet adherence variable.",
		exam="BP 135/85, pulse 78. Foot examination normal.",
		vitals=dict(sys_bp=135, dia_bp=85, pulse=78, resp_rate=15, spo2=98, temperature=36.7, blood_glucose=168, weight=88, height=170),
		diagnoses=[("E11.9", "Type 2 diabetes mellitus without complications", "Primary")],
		plan="HbA1c and fasting glucose. Continue metformin, add statin. Dietitian referral.",
		prescriptions=[("LXH-MET", "500 mg", "Twice daily with meals", 30, 3), ("LXH-ATOR", "20 mg", "Once daily at night", 30, 1)],
		labs=["LAB-HBA1C", "LAB-GLU"], radiology=[], procedures=[],
		lab_values={"LAB-HBA1C": {"HbA1c": "8.1"}, "LAB-GLU": {"Fasting Glucose": "168"}}, reports={}, pay=True, claim=0.5),
}
# Upcoming appointments (booked, not yet seen): patient, doctor, branch, days ahead, time, reason
UPCOMING = [
	("fatma", "Dr. Ahmed Hassan", "Cairo Hospital", 1, "10:00:00", "Demo: blood pressure review"),
	("nour", "Dr. Omar Ibrahim", "Alexandria Clinic", 1, "10:30:00", "Demo: recurrent headache"),
	("lama", "Dr. Noura Al-Harbi", "Riyadh Hospital", 1, "09:30:00", "Demo: recurring cough"),
]
# Inpatient stories
STAYS = {
	"salma": dict(patient="salma", doctor="Dr. Ahmed Hassan", branch="Cairo Hospital", ward="Cairo Private Floor", bed="P-201", days_ago=3, diagnosis="Demo: community-acquired pneumonia",
		deposit=4000, discharge=("Recovered", "Treated with IV antibiotics for three days. Fever resolved, chest X-ray improved. Discharged on oral antibiotics."),
		complaint="Fever, productive cough and right chest pain for four days.",
		history="26-year-old, previously healthy. No known drug allergy.", exam="Temperature 38.9, crackles right base, SpO2 92% on room air.",
		vitals=dict(sys_bp=110, dia_bp=70, pulse=112, resp_rate=24, spo2=92, temperature=38.9, weight=62, height=165),
		diagnoses=[("J18.9", "Pneumonia, unspecified organism", "Primary")], plan="IV amoxicillin/clavulanate, IV fluids, paracetamol, oxygen as needed. Repeat CBC and CRP.",
		prescriptions=[("LXH-AUG", "1 g", "Every 12 hours", 5, 3), ("LXH-PARA", "500 mg", "Every 8 hours", 3, 2), ("LXH-NS", "500 ml", "Over 6 hours", 3, 4)],
		labs=["LAB-CBC", "LAB-CRP"], radiology=[("RAD-XR-CHEST", "Chest", "Fever and productive cough")], procedures=[("PRC-IVINF", 3)],
		lab_values={"LAB-CBC": {"Hemoglobin": "12.8", "WBC": "15.2", "Platelets": "310"}, "LAB-CRP": {"CRP": "86"}},
		reports={"RAD-XR-CHEST": ("Right lower zone consolidation with air bronchogram. No effusion.", "Right lower lobe pneumonia.")}, claim=0.0),
	"ali": dict(patient="ali", doctor="Dr. Ahmed Hassan", branch="Cairo Hospital", ward="Cairo General Ward", bed="G-101", days_ago=1, diagnosis="Demo: acute exacerbation of COPD",
		deposit=3000, discharge=None,
		complaint="Worsening breathlessness and cough with sputum for three days.", history="65-year-old ex-smoker with COPD and hypertension.",
		exam="Wheeze bilaterally, prolonged expiration, SpO2 90% on room air.",
		vitals=dict(sys_bp=145, dia_bp=90, pulse=98, resp_rate=26, spo2=90, temperature=37.6, weight=78, height=172),
		diagnoses=[("J44.1", "COPD with acute exacerbation", "Primary")], plan="Nebulized bronchodilators, steroids, antibiotics, oxygen. Monitor.",
		prescriptions=[("LXH-SALB", "4 puffs", "Every 4 hours", 5, 1), ("LXH-AMOX", "500 mg", "Every 8 hours", 5, 2)],
		labs=["LAB-CBC"], radiology=[], procedures=[],
		lab_values={"LAB-CBC": {"Hemoglobin": "15.1", "WBC": "12.6", "Platelets": "228"}}, reports={}, claim=None),
}


def _say(msg):
	print(msg)


def _get(doctype, filters, field="name"):
	return frappe.db.get_value(doctype, filters, field)


def _insert(doc):
	return frappe.get_doc(doc).insert(ignore_permissions=True)


def _ccy(company):
	return frappe.db.get_value("Company", company, "default_currency")


def _mode(company, prefer=("Cash",)):
	"""A Mode of Payment that has an account for the company: a standard one when it has, else a demo mode created with the company's default cash account."""
	for m in prefer:
		if frappe.db.exists("Mode of Payment Account", {"parent": m, "company": company}):
			return m
	acct = frappe.db.get_value("Company", company, "default_cash_account")
	if not acct:
		frappe.throw(f"Company {company} has no default cash account")
	if not frappe.db.exists("Mode of Payment", "Demo Cash"):
		_insert({"doctype": "Mode of Payment", "mode_of_payment": "Demo Cash", "type": "Cash", "enabled": 1})
	mode = frappe.get_doc("Mode of Payment", "Demo Cash")
	if not any(r.company == company for r in mode.accounts):
		mode.append("accounts", {"company": company, "default_account": acct})
		mode.save(ignore_permissions=True)
	return "Demo Cash"


def _doctor(name):
	d = _get("Hospital Doctor", {"doctor_name": name})
	if not d:
		frappe.throw(f"Doctor {name} does not exist")
	return d


def _patient(key):
	p = _get("Hospital Patient", {"patient_name": PATIENTS[key]["name"]})
	if not p:
		frappe.throw(f"Patient {PATIENTS[key]['name']} does not exist")
	return p


def _service_item(code):
	return frappe.db.get_value("Hospital Service", code, "item")


# ------------------------------------------------------------------ masters
def _settings(_x):
	"""Fill the Hospital Settings the demo needs, only where they are empty (set values are never overwritten)."""
	cur = frappe.get_doc("Hospital Settings")
	_price_list(PL_EGP)
	for field, doctype, value in (("company", "Company", EGYPT), ("price_list", "Price List", PL_EGP), ("service_item_group", "Item Group", "Hospital Services")):
		if not cur.get(field) and frappe.db.exists(doctype, value):
			frappe.db.set_single_value("Hospital Settings", field, value)
	frappe.clear_document_cache("Hospital Settings", "Hospital Settings")


def _price_list(name):
	if not frappe.db.exists("Price List", name):
		_insert({"doctype": "Price List", "price_list_name": name, "currency": PRICE_LIST_CURRENCY[name], "selling": 1, "buying": 0, "enabled": 1})


def _departments(name):
	if not frappe.db.exists("Hospital Department", name):
		typ = dict(DEPARTMENTS)[name]
		_insert({"doctype": "Hospital Department", "department_name": name, "department_type": typ, "active": 1})


def _specialty(name):
	if not frappe.db.exists("Medical Specialty", name):
		_insert({"doctype": "Medical Specialty", "specialty": name})


def _service(code):
	row = next(s for s in SERVICES if s[0] == code)
	_c, name, typ, dept, egp, _sar = row
	if not frappe.db.exists("Hospital Service", code):
		_insert({"doctype": "Hospital Service", "service_code": code, "service_name": name, "service_type": typ, "department": dept, "base_price": egp,
			"needs_doctor": 1 if typ in ("Consultation", "Procedure") else 0, "active": 1, "description": name})


def _service_price(code):
	"""The cash price of a service in each branch price list (created only when missing)."""
	row = next(s for s in SERVICES if s[0] == code)
	item = _service_item(code)
	if not item:
		frappe.throw(f"Service {code} has no item")
	for pl, price in ((PL_EGP, row[4]), (PL_SAR, row[5])):
		_item_price(item, pl, price)


def _item_price(item, pl, price):
	_price_list(pl)
	if not frappe.db.exists("Item Price", {"item_code": item, "price_list": pl, "selling": 1}):
		_insert({"doctype": "Item Price", "item_code": item, "price_list": pl, "selling": 1, "uom": "Nos", "price_list_rate": price, "currency": PRICE_LIST_CURRENCY[pl]})


def _lab_template(code):
	sample, params, ranges = LAB_TEMPLATES[code]
	if frappe.db.exists("Lab Test Template", code):
		return
	doc = {"doctype": "Lab Test Template", "service": code, "sample_type": sample, "container": "EDTA tube" if sample == "Blood" else "Plain tube", "tat_hours": 4,
		"parameters": [{"parameter": p, "unit": u, "result_type": "Numeric"} for p, u in params], "ranges": []}
	for p, gender, lo, hi, clo, chi in ranges:
		r = {"parameter": p, "gender": gender}
		for k, v in (("low", lo), ("high", hi), ("crit_low", clo), ("crit_high", chi)):
			if v is not None:
				r[k] = v
		doc["ranges"].append(r)
	_insert(doc)


def _branch(name):
	_n, company, cc, wh, pl, phone, addr = next(b for b in BRANCHES if b[0] == name)
	if frappe.db.exists("Hospital Branch", name):
		return
	if not frappe.db.exists("Company", company):
		frappe.throw(f"Company {company} is missing. Run ledgerx.demo.foundation first.")
	wh = _warehouse(company, wh)
	_price_list(pl)
	_insert({"doctype": "Hospital Branch", "branch_name": name, "company": company, "cost_center": cc if frappe.db.exists("Cost Center", cc) else None, "warehouse": wh,
		"price_list": pl, "active": 1, "address": addr, "phone": phone})


def _warehouse(company, base):
	"""The hospital pharmacy warehouse of a branch ('<base> - <company abbreviation>'), created when missing."""
	full = f"{base} - {frappe.db.get_value('Company', company, 'abbr')}"
	if not frappe.db.exists("Warehouse", full):
		_insert({"doctype": "Warehouse", "warehouse_name": base, "company": company})
	return full


def _ward(name):
	_n, branch, typ, beds = next(w for w in WARDS if w[0] == name)
	ward = _get("Ward", {"ward_name": name, "branch": branch})
	if not ward:
		ward = _insert({"doctype": "Ward", "ward_name": name, "branch": branch, "ward_type": typ, "department": "Inpatient Ward", "active": 1}).name
	for no, room, cls, svc in beds:
		if not _get("Hospital Bed", {"ward": ward, "bed_no": no}):
			_insert({"doctype": "Hospital Bed", "bed_no": no, "ward": ward, "room_no": room, "bed_class": cls, "charge_service": svc, "status": "Available", "active": 1})


def _doctor_master(name):
	if _get("Hospital Doctor", {"doctor_name": name}):
		return
	_n, spec, dept, default_branch, sched, cons, lic, mobile = next(d for d in DOCTORS if d[0] == name)
	doc = {"doctype": "Hospital Doctor", "doctor_name": name, "specialty": spec, "department": dept, "default_branch": default_branch, "mobile": mobile, "license_no": lic,
		"followup_days": 14, "active": 1, "consultation_service": cons, "branches": [{"branch": b} for b in dict.fromkeys(s[0] for s in sched)] or [{"branch": default_branch}],
		"schedule": [{"weekday": wd, "branch": b, "from_time": a, "to_time": z, "slot_minutes": 15, "capacity": 1} for b, a, z in sched for wd in WEEKDAYS],
		"fee_rules": [{"service_type": t, "payer": "All", "mode": "Percent", "value": v} for t, v in FEE_RULES if (t != "Radiology") == (spec != "Radiology")]}
	_insert(doc)


def _insurer(name):
	if not frappe.db.exists("Hospital Insurer", name):
		days = dict(INSURERS)[name]
		_insert({"doctype": "Hospital Insurer", "company_name": name, "claim_days": days, "active": 1, "contact": "Claims desk"})


def _plan(name):
	_n, insurer, cover, copay, cap, annual, rules = next(p for p in PLANS if p[0] == name)
	if frappe.db.exists("Hospital Insurance Plan", name):
		return
	_insert({"doctype": "Hospital Insurance Plan", "plan_name": name, "insurance_company": insurer, "active": 1, "valid_from": add_days(nowdate(), -120), "valid_to": add_days(nowdate(), 245),
		"cover_pct": cover, "visit_copay": copay, "patient_cap": cap, "annual_limit": annual,
		"rules": [{"service": s, "service_type": t, "cover_pct": c, "requires_approval": a, "excluded": x} for s, t, c, a, x in rules]})


# ------------------------------------------------------------------ medicines and stock
def _medicine_group(_x):
	if not frappe.db.exists("Item Group", MEDICINE_GROUP):
		_insert({"doctype": "Item Group", "item_group_name": MEDICINE_GROUP, "parent_item_group": "All Item Groups", "is_group": 0})


def _medicine(code):
	_c, name, egp, sar, _ce, _cs = next(m for m in MEDICINES if m[0] == code)
	if not frappe.db.exists("Item", code):
		_insert({"doctype": "Item", "item_code": code, "item_name": name, "item_group": MEDICINE_GROUP, "stock_uom": "Nos", "is_stock_item": 1, "has_batch_no": 1, "create_new_batch": 0,
			"has_expiry_date": 1, "shelf_life_in_days": 730, "is_sales_item": 1, "is_purchase_item": 1, "standard_rate": egp, "description": name})
	_item_price(code, PL_EGP, egp)
	_item_price(code, PL_SAR, sar)


def _batches(code):
	"""Two lots per medicine: one near expiry (used first by FEFO) and one long-dated."""
	for suffix, months in (("A", 4), ("B", 20)):
		bid = f"{code}-{suffix}2611"
		if not frappe.db.exists("Batch", bid):
			_insert({"doctype": "Batch", "batch_id": bid, "item": code, "manufacturing_date": add_months(nowdate(), months - 24), "expiry_date": add_months(nowdate(), months)})


def _stock(branch):
	"""Opening stock of every demo medicine in the branch warehouse, as one real Material Receipt."""
	_n, company, cc, wh, _pl, _p, _a = next(b for b in BRANCHES if b[0] == branch)
	wh = _warehouse(company, wh)
	remark = f"Demo hospital opening stock - {wh}"
	if frappe.db.exists("Stock Entry", {"remarks": remark, "docstatus": 1}):
		return
	account = frappe.db.get_value("Company", company, "stock_adjustment_account")
	if not account:
		frappe.throw(f"Set the stock adjustment account on {company}")
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.company = company
	se.posting_date = nowdate()
	se.set_posting_time = 1
	se.to_warehouse = wh
	se.remarks = remark
	egp = company == EGYPT
	for code, _name, _pe, _ps, cost_egp, cost_sar in MEDICINES:
		for suffix, qty in (("A", 40), ("B", 200)):
			row = {"item_code": code, "qty": qty, "uom": "Nos", "stock_uom": "Nos", "conversion_factor": 1, "t_warehouse": wh, "basic_rate": cost_egp if egp else cost_sar,
				"batch_no": f"{code}-{suffix}2611", "use_serial_batch_fields": 1, "expense_account": account}
			if frappe.db.exists("Cost Center", cc):
				row["cost_center"] = cc
			se.append("items", row)
	se.insert(ignore_permissions=True)
	se.submit()


# ------------------------------------------------------------------ patients and appointments
def _patient_master(key):
	p = PATIENTS[key]
	if _get("Hospital Patient", {"patient_name": p["name"]}):
		return
	ename, ephone, erel = p["emergency"]
	doc = {"doctype": "Hospital Patient", "patient_name": p["name"], "gender": p["gender"], "mobile": p["mobile"], "city": p["city"], "address": p.get("address"), "branch": p["branch"],
		"blood_group": p.get("blood_group"), "chronic_conditions": p.get("chronic"), "allergies": p.get("allergies"), "emergency_name": ename, "emergency_phone": ephone,
		"emergency_relation": erel, "status": "Active", "marital_status": "Married" if p["gender"] == "Male" and key in ("mahmoud", "ali", "abdulrahman") else None}
	if p.get("national_id"):
		doc["national_id"] = p["national_id"]
	else:
		doc["passport_no"], doc["date_of_birth"] = p["passport_no"], p["dob"]
	if p.get("plan"):
		doc.update({"insurance_plan": p["plan"], "member_no": p["member_no"], "insurance_expiry": add_days(nowdate(), 245)})
	_insert(doc)


def _upcoming(i):
	key, doctor, branch, days, time, reason = UPCOMING[int(i)]
	pat = _patient(key)
	if frappe.db.exists("Patient Appointment", {"patient": pat, "reason": reason}):
		return
	_insert({"doctype": "Patient Appointment", "patient": pat, "doctor": _doctor(doctor), "branch": branch, "appointment_date": add_days(nowdate(), days), "from_time": time,
		"appointment_type": "Consultation", "status": "Scheduled", "reason": reason})


# ------------------------------------------------------------------ clinical flow
def _approval(patient, plan, branch, spec):
	number, service, amount = spec
	if frappe.db.exists("Insurance Approval", {"patient": patient, "approval_no": number}):
		return
	_insert({"doctype": "Insurance Approval", "patient": patient, "insurance_plan": plan, "branch": branch, "requested_on": nowdate(), "status": "Approved", "approval_no": number,
		"valid_till": add_days(nowdate(), 30), "services": [{"service": service, "max_amount": amount}], "notes": "Pre-authorisation for CT chest"})


def _fill_encounter(enc_name, v, patient, branch):
	"""Writes the doctor's notes, vitals, diagnoses, orders and prescriptions into an open encounter and completes it."""
	enc = frappe.get_doc("Patient Encounter", enc_name)
	enc.chief_complaint, enc.history, enc.examination, enc.plan = v["complaint"], v["history"], v["exam"], v["plan"]
	for code, name, typ in v["diagnoses"]:
		enc.append("diagnoses", {"icd_code": code, "diagnosis": name, "diagnosis_type": typ})
	for item, dosage, freq, days, qty in v["prescriptions"]:
		enc.append("prescriptions", {"item_code": item, "dosage": dosage, "frequency": freq, "duration_days": days, "qty": qty})
	for svc in v["labs"]:
		enc.append("lab_tests", {"service": svc, "urgent": 0})
	for svc, part, info in v["radiology"]:
		enc.append("radiology", {"service": svc, "body_part": part, "clinical_info": info})
	for svc, qty in v["procedures"]:
		enc.append("procedures", {"service": svc, "qty": qty})
	if v.get("followup"):
		enc.followup_date = add_days(nowdate(), v["followup"])
	vs = _insert({"doctype": "Vital Signs", "patient": patient, "branch": branch, "encounter": enc.name, "admission": enc.admission, **v["vitals"]})
	enc.vitals = vs.name
	enc.save(ignore_permissions=True)
	enc.complete()
	return enc.name


def _results(enc_name, v):
	"""Collects the samples, enters and verifies lab results, performs and reports the radiology orders of an encounter."""
	for order in frappe.get_all("Lab Order", filters={"encounter": enc_name}, pluck="name"):
		for row in frappe.get_doc("Lab Order", order).tests:
			values = v["lab_values"].get(row.service)
			if not values or row.status != "Ordered":
				continue
			lr = frappe.get_doc("Lab Result", frappe.get_doc("Lab Order", order).collect_sample(row.name))
			for r in lr.result_values:
				r.value = values[r.parameter]
			lr.save(ignore_permissions=True)
			lr.mark_resulted()
			lr.verify()
	radiologist = _get("Hospital Doctor", {"doctor_name": "Dr. Heba Saleh"})
	for ro in frappe.get_all("Radiology Order", filters={"encounter": enc_name, "status": "Ordered"}, fields=["name", "service"]):
		report = v["reports"].get(ro.service)
		if not report:
			continue
		doc = frappe.get_doc("Radiology Order", ro.name)
		doc.modality = MODALITY.get(ro.service, "Other")
		doc.radiologist = radiologist
		doc.perform("Mostafa Adel")
		doc.report(report[0], report[1], 0)
		doc.verify()


def _dispense(enc_name, patient, branch, doctor, admission=None):
	enc = frappe.get_doc("Patient Encounter", enc_name)
	items = [{"item_code": r.item_code, "qty": r.qty or 1, "prescription_row": r.name} for r in enc.prescriptions if not r.dispensed]
	if not items:
		return None
	d = _insert({"doctype": "Medication Dispense", "patient": patient, "branch": branch, "posting_date": nowdate(), "encounter": enc_name, "admission": admission, "doctor": doctor, "items": items})
	d.submit()
	return d.name


def _bill_and_pay(patient, branch, plan, admission=None, pay=True):
	"""One bill of every unbilled charge (insurer invoice and patient invoice are made by the billing engine); the patient then pays what is left."""
	if frappe.db.exists("Hospital Bill", {"patient": patient, "docstatus": ["!=", 2]}):
		return frappe.db.get_value("Hospital Bill", {"patient": patient, "docstatus": ["!=", 2]}, "name")
	names = [c.name for c in billing.unbilled(patient, admission, branch)]
	if not names:
		return None
	bill = _insert({"doctype": "Hospital Bill", "patient": patient, "branch": branch, "posting_date": nowdate(), "admission": admission, "insurance_plan": plan,
		"lines": [{"charge": n} for n in names]})
	bill.submit()
	bill.reload()
	if pay and bill.patient_invoice:
		owed = flt(frappe.db.get_value("Sales Invoice", bill.patient_invoice, "outstanding_amount"))
		if owed > 0:
			billing.receive_payment(bill.name, owed, _mode(bill.company), "DEMO-CASH-" + bill.name)
	return bill.name


def _claim(bill_name, fraction):
	"""A claim to the insurer for the bill, sent; the insurer then pays `fraction` of it (0 = unpaid yet)."""
	bill = frappe.get_doc("Hospital Bill", bill_name)
	if not (bill.insurer_invoice and bill.insurance_plan) or bill.claim:
		return
	insurer = frappe.db.get_value("Hospital Insurance Plan", bill.insurance_plan, "insurance_company")
	claim = _insert({"doctype": "Insurance Claim", "insurance_company": insurer, "branch": bill.branch, "from_date": add_days(bill.posting_date, -30), "to_date": bill.posting_date,
		"notes": "Demo claim", "lines": [{"bill": bill.name}]})
	claim.submit_claim()
	if fraction:
		amount = round(flt(bill.insurer_total) * fraction, 2)
		claim.reload()
		claim.register_payment(amount, _mode(bill.company, ("Wire Transfer", "Bank Draft", "Cash")), "DEMO-" + claim.name)


def _visit(key):
	v = VISITS[key]
	pat, doctor, branch = _patient(v["patient"]), _doctor(v["doctor"]), v["branch"]
	if frappe.db.exists("Patient Appointment", {"patient": pat, "reason": v["reason"]}):
		return
	plan = _get("Hospital Patient", pat, "insurance_plan")
	if v.get("approval"):
		_approval(pat, plan, branch, v["approval"])
	appt = _insert({"doctype": "Patient Appointment", "patient": pat, "doctor": doctor, "branch": branch, "appointment_date": add_days(nowdate(), v["day"]), "from_time": v["time"],
		"appointment_type": "Consultation", "status": "Scheduled", "reason": v["reason"]})
	appt.check_in()
	enc = _fill_encounter(appt.start_encounter(), v, pat, branch)
	_results(enc, v)
	_dispense(enc, pat, branch, doctor)
	bill = _bill_and_pay(pat, branch, plan, pay=v.get("pay", True))
	if bill and v.get("claim") is not None:
		_claim(bill, v["claim"])
	if v.get("followup_reason"):
		_insert({"doctype": "Patient Appointment", "patient": pat, "doctor": doctor, "branch": branch, "appointment_date": add_days(nowdate(), v["followup"]), "from_time": "10:15:00",
			"appointment_type": "Follow-up", "status": "Scheduled", "reason": v["followup_reason"]})


def _stay(key):
	s = STAYS[key]
	pat, doctor, branch = _patient(s["patient"]), _doctor(s["doctor"]), s["branch"]
	if frappe.db.exists("Inpatient Admission", {"patient": pat, "diagnosis": s["diagnosis"]}):
		return
	plan = _get("Hospital Patient", pat, "insurance_plan")
	ward = _get("Ward", {"ward_name": s["ward"], "branch": branch})
	bed = _get("Hospital Bed", {"ward": ward, "bed_no": s["bed"]})
	if not bed:
		frappe.throw(f"Bed {s['bed']} does not exist")
	company = frappe.db.get_value("Hospital Branch", branch, "company")
	mode = _mode(company)
	pe = billing.receive_deposit(pat, branch, s["deposit"], mode, None, "DEMO-DEP-" + s["patient"])
	adm = _insert({"doctype": "Inpatient Admission", "patient": pat, "branch": branch, "admitting_doctor": doctor, "department": "Inpatient Ward", "admission_type": "Emergency",
		"admitted_on": add_to_date(now_datetime(), days=-s["days_ago"]), "bed": bed, "diagnosis": s["diagnosis"], "expected_discharge": add_days(nowdate(), 2), "insurance_plan": plan,
		"deposits": [{"posting_date": nowdate(), "amount": s["deposit"], "mode_of_payment": mode, "payment_entry": pe}]})
	enc = _insert({"doctype": "Patient Encounter", "patient": pat, "doctor": doctor, "branch": branch, "encounter_type": "Inpatient Round", "admission": adm.name,
		"encounter_date": add_to_date(now_datetime(), days=-max(s["days_ago"] - 1, 0)), "insurance_plan": plan})
	enc_name = _fill_encounter(enc.name, s, pat, branch)
	_results(enc_name, s)
	_dispense(enc_name, pat, branch, doctor, adm.name)
	if s.get("discharge"):
		frappe.get_doc("Inpatient Admission", adm.name).discharge(*s["discharge"])
		bill = _bill_and_pay(pat, branch, plan, admission=adm.name)
		if bill and s.get("claim") is not None:
			_claim(bill, s["claim"])


STEPS = [
	("Settings and price lists", _settings, [1]),
	("Departments", _departments, [d[0] for d in DEPARTMENTS]),
	("Specialties", _specialty, SPECIALTIES),
	("Services", _service, [s[0] for s in SERVICES]),
	("Service prices", _service_price, [s[0] for s in SERVICES]),
	("Lab test templates", _lab_template, list(LAB_TEMPLATES)),
	("Branches", _branch, [b[0] for b in BRANCHES]),
	("Wards and beds", _ward, [w[0] for w in WARDS]),
	("Doctors", _doctor_master, [d[0] for d in DOCTORS]),
	("Insurers", _insurer, [i[0] for i in INSURERS]),
	("Insurance plans", _plan, [p[0] for p in PLANS]),
	("Medicine group", _medicine_group, [1]),
	("Medicines and prices", _medicine, [m[0] for m in MEDICINES]),
	("Medicine batches", _batches, [m[0] for m in MEDICINES]),
	("Opening stock", _stock, [b[0] for b in BRANCHES]),
	("Patients", _patient_master, list(PATIENTS)),
	("Upcoming appointments", _upcoming, [str(i) for i in range(len(UPCOMING))]),
	("Outpatient stories", _visit, list(VISITS)),
	("Inpatient stories", _stay, list(STAYS)),
]


def run():
	_say("Hospital demo data")
	failed_any = False
	for label, fn, items in STEPS:
		done, failed = run_each(items, fn, f"Demo hospital: {label}")
		failed_any = failed_any or bool(failed)
		_say(f"  {label}: {len(done)} ok, {len(failed)} failed")
	if failed_any:
		_say("Some steps failed. Open Error Log (titles start with 'Demo hospital') and send me the errors.")
	else:
		_say("Done. Open the Hospital workspace: bed board, appointments, charges, bills and claims are filled.")
