"""Database readers and small shared helpers. Everything here is safe to call from any controller."""
import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate


def settings():
	return frappe.get_cached_doc("Hospital Settings")


def branch_doc(name):
	if not name:
		frappe.throw(_("Choose a branch"))
	return frappe.get_cached_doc("Hospital Branch", name)


def is_manager(user=None):
	roles = frappe.get_roles(user)
	return "System Manager" in roles or "Hospital Manager" in roles


def company_of(branch):
	return branch_doc(branch).company


# ------------------------------------------------------------------ people
def patient_customer(patient):
	"""The Customer behind a patient (created on first use). Invoices and payments are posted to it."""
	cust = frappe.db.get_value("Hospital Patient", patient, "customer")
	if cust and frappe.db.exists("Customer", cust):
		return cust
	name = frappe.db.get_value("Hospital Patient", patient, "patient_name")
	group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	if not (group and territory):
		frappe.throw(_("Create a Customer Group and a Territory first"))
	c = frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Individual", "customer_group": group, "territory": territory})
	c.flags.ignore_mandatory = True
	c.insert(ignore_permissions=True)
	frappe.db.set_value("Hospital Patient", patient, "customer", c.name, update_modified=False)
	return c.name


def insurer_customer(plan):
	company = frappe.db.get_value("Hospital Insurance Plan", plan, "insurance_company")
	cust = frappe.db.get_value("Hospital Insurer", company, "customer")
	if not cust:
		frappe.throw(_("Insurance company {0} has no customer. Save it again.").format(company))
	return cust


def doctor_user(doctor):
	return frappe.db.get_value("Hospital Doctor", doctor, "user") if doctor else None


# ------------------------------------------------------------------ prices
def _price_row(item_code, price_list, on_date):
	if not (item_code and price_list):
		return None
	rows = frappe.get_all("Item Price", filters={"item_code": item_code, "price_list": price_list, "selling": 1},
		fields=["price_list_rate", "valid_from", "valid_upto"], order_by="valid_from desc, creation desc")
	d = getdate(on_date or nowdate())
	for r in rows:
		if r.valid_from and getdate(r.valid_from) > d:
			continue
		if r.valid_upto and getdate(r.valid_upto) < d:
			continue
		return flt(r.price_list_rate)
	return None


def cash_price_list(branch=None):
	pl = frappe.db.get_value("Hospital Branch", branch, "price_list") if branch else None
	return pl or settings().price_list


def item_price(item_code, plan=None, branch=None, on_date=None, fallback=None):
	"""Price of an item for a patient: the plan's price list, else the cash list less the plan discount, else `fallback`.
	Returns (price, source) where source is 'plan', 'cash', 'plan discount' or 'service'."""
	if plan:
		pl, disc = frappe.db.get_value("Hospital Insurance Plan", plan, ["price_list", "discount_pct"])
		p = _price_row(item_code, pl, on_date)
		if p is not None:
			return p, "plan"
		base = _price_row(item_code, cash_price_list(branch), on_date)
		if base is None and fallback is not None:
			base, src = flt(fallback), "service"
		else:
			src = "cash"
		if base is not None:
			return round(base * (1 - flt(disc) / 100.0), 2), ("plan discount" if flt(disc) else src)
		return None, None
	p = _price_row(item_code, cash_price_list(branch), on_date)
	if p is not None:
		return p, "cash"
	if fallback is not None:
		return flt(fallback), "service"
	return None, None


def service_price(service, plan=None, branch=None, on_date=None):
	svc = frappe.db.get_value("Hospital Service", service, ["item", "base_price", "active"], as_dict=1)
	if not svc:
		frappe.throw(_("Service {0} does not exist").format(service))
	if not svc.active:
		frappe.throw(_("Service {0} is not active").format(service))
	price, _src = item_price(svc.item, plan, branch, on_date, fallback=svc.base_price)
	return flt(price)


def find_approval(patient, plan, service, on_date=None):
	"""An Approved (or Partially Approved) insurance approval of this patient and plan that is still valid and lists the service."""
	if not (patient and plan and service):
		return None
	d = getdate(on_date or nowdate())
	rows = frappe.db.sql("""SELECT a.name FROM `tabInsurance Approval` a INNER JOIN `tabApproval Service` s ON s.parent = a.name
		WHERE a.patient = %s AND a.insurance_plan = %s AND s.service = %s AND a.status IN ('Approved', 'Partially Approved')
		AND (a.valid_till IS NULL OR a.valid_till >= %s) ORDER BY a.creation DESC LIMIT 1""", (patient, plan, service, d))
	return rows[0][0] if rows else None


def plan_dict(plan):
	"""An Insurance Plan as the plain dict the billing engine reads."""
	p = frappe.get_cached_doc("Hospital Insurance Plan", plan)
	return {"cover_pct": flt(p.cover_pct), "patient_cap": p.patient_cap or None, "visit_copay": flt(p.visit_copay),
		"rules": [{"service": r.service, "service_type": r.service_type, "cover_pct": r.cover_pct if r.cover_pct not in (None, "") else None, "copay_fixed": flt(r.copay_fixed),
			"line_cap": flt(r.line_cap), "requires_approval": cint(r.requires_approval), "excluded": cint(r.excluded)} for r in p.rules]}


def check_plan_usable(plan, on_date=None):
	p = frappe.get_cached_doc("Hospital Insurance Plan", plan)
	d = getdate(on_date or nowdate())
	if not p.active:
		frappe.throw(_("Insurance plan {0} is not active").format(plan))
	if p.valid_from and getdate(p.valid_from) > d:
		frappe.throw(_("Insurance plan {0} starts on {1}").format(plan, p.valid_from))
	if p.valid_to and getdate(p.valid_to) < d:
		frappe.throw(_("Insurance plan {0} expired on {1}").format(plan, p.valid_to))
	if not frappe.db.get_value("Hospital Insurer", p.insurance_company, "active"):
		frappe.throw(_("Insurance company {0} is not active").format(p.insurance_company))
	return p


def annual_remaining(plan, patient, on_date=None, exclude_bill=None):
	"""What is left of the member's annual limit, or None when the plan has no limit. The year is the plan's validity period when it has one, else the calendar year."""
	p = frappe.get_cached_doc("Hospital Insurance Plan", plan)
	if not flt(p.annual_limit):
		return None
	d = getdate(on_date or nowdate())
	start, end = (p.valid_from, p.valid_to) if (p.valid_from and p.valid_to) else (f"{d.year}-01-01", f"{d.year}-12-31")
	used = frappe.db.sql("""SELECT COALESCE(SUM(insurer_total), 0) FROM `tabHospital Bill` WHERE docstatus = 1 AND patient = %s AND insurance_plan = %s
		AND posting_date BETWEEN %s AND %s AND name != %s""", (patient, plan, start, end, exclude_bill or ""))[0][0]
	return max(flt(p.annual_limit) - flt(used), 0)


# ------------------------------------------------------------------ stock
BATCH_SQL = """
	SELECT sbe.batch_no AS batch_no, sbe.warehouse AS warehouse, b.item AS item_code, b.expiry_date AS expiry, SUM(sbe.qty) AS qty
	FROM `tabSerial and Batch Entry` sbe
	INNER JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbe.parent
	INNER JOIN `tabBatch` b ON b.name = sbe.batch_no
	WHERE sle.is_cancelled = 0 {where}
	GROUP BY sbe.batch_no, sbe.warehouse
	HAVING SUM(sbe.qty) > 0.000001
"""


def batch_stock(warehouses, item_code=None):
	warehouses = [w for w in (warehouses or []) if w]
	if not warehouses:
		return []
	where, vals = "AND sbe.warehouse IN %(wh)s", {"wh": tuple(warehouses)}
	if item_code:
		where += " AND b.item = %(item)s"
		vals["item"] = item_code
	rows = frappe.db.sql(BATCH_SQL.format(where=where), vals, as_dict=1)
	for r in rows:
		r["expiry"] = getdate(r["expiry"]) if r.get("expiry") else None
		r["qty"] = flt(r["qty"])
	return rows


def fefo(item_code, warehouse, qty, today=None, min_days=0):
	"""Allocate `qty` (stock units) of an item from a warehouse, nearest expiry first. Returns (allocations, shortfall)."""
	from ledgerx_hospital.engine.stock import fefo_allocate

	today = getdate(today or nowdate())
	if not cint(frappe.db.get_value("Item", item_code, "has_batch_no")):
		have = flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))
		take = min(have, qty)
		return ([(None, take)] if take > 0 else []), max(qty - take, 0)
	rows = [{"batch_no": r["batch_no"], "qty": r["qty"], "expiry": r["expiry"]} for r in batch_stock([warehouse], item_code)]
	return fefo_allocate(rows, qty, today, min_days)


def item_info(item_code):
	d = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom", "has_batch_no", "is_stock_item", "disabled", "description"], as_dict=1)
	if not d:
		frappe.throw(_("Item {0} does not exist").format(item_code))
	return d


def ingredient_of(item_code):
	"""The active ingredient of an item when the pharmacy app is installed, else its name: used by the prescription checks."""
	if frappe.get_meta("Item").has_field("ph_active_ingredient"):
		v = frappe.db.get_value("Item", item_code, "ph_active_ingredient")
		if v:
			return v
	return ""



def insurer_customer_of(company):
	cust = frappe.db.get_value("Hospital Insurer", company, "customer")
	if not cust:
		frappe.throw(_("Insurance company {0} has no customer. Save it again.").format(company))
	return cust
