"""Charge capture: every department records what it did as a Hospital Charge; the bill collects them later.
add_charge is idempotent per source, so a button pressed twice or a retried job never charges twice."""
import frappe
from frappe import _
from frappe.utils import flt, nowdate

from ledgerx_hospital import data
from ledgerx_hospital.engine.billing import line_net


def existing(source_doctype, source_name):
	if not (source_doctype and source_name):
		return None
	return frappe.db.get_value("Hospital Charge", {"source_doctype": source_doctype, "source_name": source_name, "status": ["!=", "Cancelled"]}, "name")


def add_charge(patient, branch, service=None, item_code=None, qty=1, rate=None, description=None, doctor=None, source_doctype=None, source_name=None,
	admission=None, encounter=None, insurance_plan=None, posting_date=None, discount_pct=0, rate_factor=1.0):
	"""Records one charge and returns its name. A service charge is priced from the patient's plan or the cash list; a medicine/item charge from the item price."""
	if source_doctype and source_name:
		found = existing(source_doctype, source_name)
		if found:
			return found
	if not (service or item_code):
		frappe.throw(_("A charge needs a service or an item"))
	plan = insurance_plan or None
	if plan and not frappe.db.exists("Hospital Insurance Plan", plan):
		plan = None
	on_date = posting_date or nowdate()
	svc = frappe.db.get_value("Hospital Service", service, ["item", "service_type", "department", "service_name"], as_dict=1) if service else None
	if service and not svc:
		frappe.throw(_("Service {0} does not exist").format(service))
	code = svc.item if svc else item_code
	if rate is None:
		if service:
			rate = data.service_price(service, plan, branch, on_date)
		else:
			price, _src = data.item_price(code, plan, branch, on_date)
			if price is None:
				frappe.throw(_("Item {0} has no selling price. Add an Item Price in the price list.").format(code))
			rate = price
	rate = round(flt(rate) * flt(rate_factor), 2)
	doc = frappe.get_doc({
		"doctype": "Hospital Charge", "patient": patient, "branch": branch, "posting_date": on_date, "service": service, "item_code": code,
		"description": description or (svc.service_name if svc else frappe.db.get_value("Item", code, "item_name")), "service_type": svc.service_type if svc else "Pharmacy",
		"department": svc.department if svc else None, "doctor": doctor, "qty": qty, "rate": rate, "discount_pct": discount_pct, "source_doctype": source_doctype,
		"source_name": source_name, "admission": admission, "encounter": encounter, "insurance_plan": plan,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def cancel_charge(name):
	"""Cancels an unbilled charge. A billed charge cannot be cancelled here: the bill has to be cancelled first."""
	if not name:
		return
	status = frappe.db.get_value("Hospital Charge", name, "status")
	if status == "Cancelled":
		return
	if status == "Billed":
		bill = frappe.db.get_value("Hospital Charge", name, "bill")
		frappe.throw(_("Charge {0} is already on bill {1}. Cancel the bill first.").format(name, bill))
	frappe.db.set_value("Hospital Charge", name, "status", "Cancelled")


def cancel_for_source(source_doctype, like):
	"""Cancels the unbilled charges whose source starts with `like` (an order and all its rows)."""
	for name in frappe.get_all("Hospital Charge", filters={"source_doctype": source_doctype, "source_name": ["like", like + "%"], "status": ["!=", "Cancelled"]}, pluck="name"):
		cancel_charge(name)


def net(qty, rate, discount_pct=0):
	return line_net(rate, qty, discount_pct)
