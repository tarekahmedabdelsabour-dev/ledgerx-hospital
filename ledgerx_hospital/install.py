"""Install and migrate steps. Each is idempotent and a failing step never aborts a migrate."""
import os

import frappe

MODULE = "Hospital"
FOLDER = "hospital"
ROLES = ["Hospital Manager", "Hospital Doctor", "Hospital Nurse", "Hospital Reception", "Hospital Lab", "Hospital Radiology", "Hospital Pharmacist", "Hospital Cashier", "Hospital Insurance"]
WALK_IN = "Hospital Walk-in"
FEE_ITEM = "Doctor Fees"
SERVICES_GROUP = "Hospital Services"

SPECIALTIES = ["General Practice", "Internal Medicine", "Pediatrics", "Obstetrics and Gynecology", "General Surgery", "Orthopedics", "Cardiology", "Neurology", "ENT", "Ophthalmology",
	"Dermatology", "Urology", "Dentistry", "Psychiatry", "Radiology", "Anesthesia", "Emergency Medicine", "Chest", "Gastroenterology", "Oncology"]
PREOP = ["Surgical consent signed", "Anesthesia consent signed", "Fasting confirmed", "Allergies checked", "Surgical site marked", "Blood tests reviewed", "Blood available if needed"]

FIELDS = [
	("Sales Invoice", "hs_section", {"label": "Hospital", "fieldtype": "Section Break", "insert_after": "more_info", "collapsible": 1}),
	("Sales Invoice", "hs_bill", {"label": "Hospital Bill", "fieldtype": "Link", "options": "Hospital Bill", "insert_after": "hs_section", "read_only": 1, "in_standard_filter": 1}),
	("Sales Invoice", "hs_patient", {"label": "Patient", "fieldtype": "Link", "options": "Hospital Patient", "insert_after": "hs_bill", "read_only": 1, "in_standard_filter": 1}),
	("Sales Invoice", "hs_col", {"fieldtype": "Column Break", "insert_after": "hs_patient"}),
	("Sales Invoice", "hs_branch", {"label": "Hospital Branch", "fieldtype": "Link", "options": "Hospital Branch", "insert_after": "hs_col", "read_only": 1, "in_standard_filter": 1}),
	("Customer", "hs_patient", {"label": "Hospital Patient", "fieldtype": "Link", "options": "Hospital Patient", "insert_after": "customer_name", "read_only": 1}),
]


def check_app_permission():
	if frappe.session.user == "Administrator":
		return True
	return bool(set(frappe.get_roles()) & set(ROLES + ["System Manager"]))


def after_install():
	_all()


def after_migrate():
	_all()


def _all():
	for fn in (ensure_module, ensure_roles, ensure_custom_fields, ensure_groups, ensure_walk_in, ensure_fee_item, ensure_lookups, ensure_settings, refresh_workspace):
		try:
			fn()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"ledgerx_hospital install step failed: {fn.__name__}")
	frappe.clear_cache()


def ensure_module():
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "ledgerx_hospital"}).insert(ignore_permissions=True)


def ensure_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_custom_fields():
	for dt, name, spec in FIELDS:
		if frappe.db.exists("DocType", dt) and not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": name}):
			frappe.get_doc({"doctype": "Custom Field", "dt": dt, "fieldname": name, **spec}).insert(ignore_permissions=True)


def ensure_groups():
	if not frappe.db.exists("Item Group", SERVICES_GROUP):
		parent = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ""}, "name") or "All Item Groups"
		frappe.get_doc({"doctype": "Item Group", "item_group_name": SERVICES_GROUP, "parent_item_group": parent, "is_group": 0}).insert(ignore_permissions=True)


def ensure_walk_in():
	if frappe.db.exists("Customer", WALK_IN):
		return
	group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	if group and territory:
		frappe.get_doc({"doctype": "Customer", "customer_name": WALK_IN, "customer_type": "Individual", "customer_group": group, "territory": territory}).insert(ignore_permissions=True)


def ensure_fee_item():
	"""The non-stock item the doctors' payable invoice is posted with."""
	if frappe.db.exists("Item", FEE_ITEM):
		return
	frappe.get_doc({"doctype": "Item", "item_code": FEE_ITEM, "item_name": FEE_ITEM, "item_group": SERVICES_GROUP, "stock_uom": "Nos", "is_stock_item": 0,
		"is_sales_item": 0, "is_purchase_item": 1}).insert(ignore_permissions=True)


def ensure_lookups():
	for s in SPECIALTIES:
		if not frappe.db.exists("Medical Specialty", s):
			frappe.get_doc({"doctype": "Medical Specialty", "specialty": s}).insert(ignore_permissions=True)


def ensure_settings():
	s = frappe.get_doc("Hospital Settings")
	changed = False
	if not s.company:
		s.company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
		changed = bool(s.company)
	if not s.price_list:
		pl = "Standard Selling" if frappe.db.exists("Price List", "Standard Selling") else frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
		if pl:
			s.price_list, changed = pl, True
	if not s.service_item_group and frappe.db.exists("Item Group", SERVICES_GROUP):
		s.service_item_group, changed = SERVICES_GROUP, True
	if not s.doctor_fee_item and frappe.db.exists("Item", FEE_ITEM):
		s.doctor_fee_item, changed = FEE_ITEM, True
	if not s.walk_in_customer and frappe.db.exists("Customer", WALK_IN):
		s.walk_in_customer, changed = WALK_IN, True
	if not s.doctor_expense_account and s.company:
		acc = frappe.db.get_value("Company", s.company, "default_expense_account")
		if acc:
			s.doctor_expense_account, changed = acc, True
	if not s.preop:
		for item in PREOP:
			s.append("preop", {"check_item": item})
		changed = True
	if changed:
		s.flags.ignore_mandatory = True
		s.save(ignore_permissions=True)


def refresh_workspace():
	"""Migrate only re-reads a workspace file that is newer than the saved one: force it."""
	base = os.path.join(frappe.get_app_path("ledgerx_hospital"), FOLDER)
	for dt in ("number_card", "dashboard_chart"):
		folder = os.path.join(base, dt)
		for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
			if os.path.isdir(os.path.join(folder, name)):
				frappe.reload_doc(FOLDER, dt, name, force=True)
	if os.path.isdir(os.path.join(base, "workspace", "hospital")):
		frappe.reload_doc(FOLDER, "workspace", "hospital", force=True)
