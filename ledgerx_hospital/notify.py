"""Alerts to people: a ToDo (shown in their desk) for critical results and similar events."""
import frappe


def todo(user, doctype, name, text, priority="High"):
	"""Creates one open ToDo for `user` about a document, once."""
	if not user:
		return None
	if frappe.db.exists("ToDo", {"allocated_to": user, "reference_type": doctype, "reference_name": name, "status": "Open", "description": text}):
		return None
	t = frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "reference_type": doctype, "reference_name": name, "description": text, "priority": priority, "status": "Open"})
	t.insert(ignore_permissions=True)
	return t.name


def users_with_role(role, branch=None):
	rows = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	return [u for u in set(rows) if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]
