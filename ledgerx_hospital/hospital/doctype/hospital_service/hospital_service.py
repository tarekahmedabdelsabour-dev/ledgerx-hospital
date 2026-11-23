import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ledgerx_hospital import data


class HospitalService(Document):
	def validate(self):
		if flt(self.base_price) < 0:
			frappe.throw(_("The price cannot be negative"))

	def after_insert(self):
		self.ensure_item()

	def on_update(self):
		self.ensure_item()
		self.sync_price()

	def ensure_item(self):
		if self.item and frappe.db.exists("Item", self.item):
			return
		group = data.settings().service_item_group or frappe.db.get_value("Item Group", "Services", "name") or frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		item = frappe.get_doc({"doctype": "Item", "item_code": self.service_code, "item_name": self.service_name, "item_group": group, "stock_uom": "Nos",
			"is_stock_item": 0, "is_sales_item": 1, "is_purchase_item": 0, "include_item_in_manufacturing": 0, "description": self.description or self.service_name})
		item.insert(ignore_permissions=True)
		self.db_set("item", item.name, update_modified=False)
		self.item = item.name

	def sync_price(self):
		pl = data.settings().price_list
		if not (self.item and pl):
			return
		cur = frappe.db.get_value("Price List", pl, "currency")
		row = frappe.db.get_value("Item Price", {"item_code": self.item, "price_list": pl, "selling": 1}, ["name", "price_list_rate"], as_dict=1)
		if row:
			if abs(flt(row.price_list_rate) - flt(self.base_price)) > 0.001:
				frappe.db.set_value("Item Price", row.name, "price_list_rate", flt(self.base_price))
		else:
			frappe.get_doc({"doctype": "Item Price", "item_code": self.item, "price_list": pl, "selling": 1, "price_list_rate": flt(self.base_price), "currency": cur}).insert(ignore_permissions=True)

	def on_trash(self):
		if frappe.db.exists("Hospital Charge", {"service": self.name}):
			frappe.throw(_("The service was used in charges. Untick Active instead of deleting it."))
