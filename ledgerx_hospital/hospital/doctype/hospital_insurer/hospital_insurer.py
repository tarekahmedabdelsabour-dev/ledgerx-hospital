import frappe
from frappe.model.document import Document


class HospitalInsurer(Document):
	def validate(self):
		if not self.customer:
			group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
			territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
			if not (group and territory):
				frappe.throw(frappe._("Create a Customer Group and a Territory first"))
			c = frappe.get_doc({"doctype": "Customer", "customer_name": self.company_name, "customer_type": "Company", "customer_group": group, "territory": territory})
			c.insert(ignore_permissions=True)
			self.customer = c.name
