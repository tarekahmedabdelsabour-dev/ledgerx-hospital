"""Stock movements for medicines and theatre consumables: first-expiry-first-out allocation, issue and return entries."""
import frappe
from frappe import _
from frappe.utils import flt, getdate

from ledgerx_hospital import data


def allocate(warehouse, lines, posting_date, min_days=0):
	"""lines: [{item_code, qty, label}] in stock units. Returns (plan, short) where plan is [(line, [(batch, qty)])] and short lists what is missing.
	The same batch is never promised twice across lines."""
	used, plan, short = {}, [], []
	for ln in lines:
		item, need = ln["item_code"], flt(ln["qty"])
		info = data.item_info(item)
		if not info.is_stock_item:
			frappe.throw(_("{0} is not a stock item").format(item))
		if need <= 0:
			frappe.throw(_("Quantity of {0} must be more than zero").format(item))
		if cint_(info.has_batch_no):
			from ledgerx_hospital.engine.stock import fefo_allocate

			rows = data.batch_stock([warehouse], item)
			left = [{"batch_no": b["batch_no"], "qty": b["qty"] - used.get((item, b["batch_no"]), 0), "expiry": b["expiry"]} for b in rows]
			alloc, miss = fefo_allocate(left, need, getdate(posting_date), min_days)
			for b, q in alloc:
				used[(item, b)] = used.get((item, b), 0) + q
		else:
			have = flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty")) - used.get((item, None), 0)
			take = max(min(have, need), 0)
			alloc, miss = ([(None, take)] if take > 0 else []), need - take
			used[(item, None)] = used.get((item, None), 0) + take
		if miss > 1e-6:
			short.append("%s: %s" % (ln.get("label") or item, flt(miss, 3)))
		plan.append((ln, alloc))
	return plan, short


def cint_(v):
	return 1 if v else 0


def cogs_account(company):
	return frappe.get_cached_value("Company", company, "default_expense_account") or frappe.get_cached_value("Company", company, "stock_adjustment_account")


def issue(company, warehouse, cost_center, plan, posting_date, remarks):
	"""Material Issue of an allocation plan. Returns the submitted Stock Entry."""
	expense = cogs_account(company)
	if not expense:
		frappe.throw(_("Set the Cost of Goods Sold account (or the stock adjustment account) on company {0}").format(company))
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.company = company
	se.posting_date = posting_date
	se.set_posting_time = 1
	se.from_warehouse = warehouse
	se.remarks = remarks
	for ln, alloc in plan:
		info = data.item_info(ln["item_code"])
		for batch, q in alloc:
			row = {"item_code": ln["item_code"], "qty": q, "uom": info.stock_uom, "stock_uom": info.stock_uom, "conversion_factor": 1, "s_warehouse": warehouse, "expense_account": expense}
			if cost_center:
				row["cost_center"] = cost_center
			if batch:
				row.update({"batch_no": batch, "use_serial_batch_fields": 1})
			se.append("items", row)
	se.insert(ignore_permissions=True)
	se.submit()
	return se


def receive(company, warehouse, cost_center, rows, posting_date, remarks):
	"""Material Receipt for returned medicines. rows: [{item_code, qty, batch_no, basic_rate}] taken from the original issue so the stock value is restored exactly."""
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.company = company
	se.posting_date = posting_date
	se.set_posting_time = 1
	se.to_warehouse = warehouse
	se.remarks = remarks
	for r in rows:
		info = data.item_info(r["item_code"])
		row = {"item_code": r["item_code"], "qty": r["qty"], "uom": info.stock_uom, "stock_uom": info.stock_uom, "conversion_factor": 1, "t_warehouse": warehouse,
			"basic_rate": flt(r.get("basic_rate")), "allow_zero_valuation_rate": 0 if flt(r.get("basic_rate")) else 1}
		if cost_center:
			row["cost_center"] = cost_center
		if r.get("batch_no"):
			row.update({"batch_no": r["batch_no"], "use_serial_batch_fields": 1})
		se.append("items", row)
	se.insert(ignore_permissions=True)
	se.submit()
	return se


def cancel_entry(name):
	if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
		se = frappe.get_doc("Stock Entry", name)
		se.flags.ignore_links = True
		se.cancel()
