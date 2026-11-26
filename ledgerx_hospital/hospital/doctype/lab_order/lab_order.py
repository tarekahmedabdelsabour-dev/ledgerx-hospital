import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from ledgerx_hospital import charges


class LabOrder(Document):
	def validate(self):
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "insurance_plan"], as_dict=1)
		self.patient_name = p.patient_name
		if not self.insurance_plan:
			self.insurance_plan = p.insurance_plan
		self.ordered_on = self.ordered_on or now_datetime()
		if not self.tests:
			frappe.throw(_("Add at least one test"))
		seen = set()
		for t in self.tests:
			if frappe.db.get_value("Hospital Service", t.service, "service_type") != "Laboratory":
				frappe.throw(_("Row {0}: {1} is not a laboratory service").format(t.idx, t.service))
			if not frappe.db.exists("Lab Test Template", t.service):
				frappe.throw(_("Row {0}: {1} has no Lab Test Template (parameters and reference ranges)").format(t.idx, t.service))
			if t.service in seen:
				frappe.msgprint(_("Row {0}: {1} appears twice").format(t.idx, t.service), indicator="orange")
			seen.add(t.service)

	def after_insert(self):
		for t in self.tests:
			if not t.charge:
				t.db_set("charge", charges.add_charge(self.patient, self.branch, service=t.service, doctor=self.ordering_doctor, source_doctype="Lab Order Test", source_name=t.name,
					admission=self.admission, encounter=self.encounter, insurance_plan=self.insurance_plan))

	@frappe.whitelist(methods=["POST"])
	def collect_sample(self, row):
		"""Marks one test's sample as collected and opens its result sheet."""
		self.check_permission("write")
		frappe.has_permission("Lab Order", "write", self, throw=True)
		t = next((x for x in self.tests if x.name == row), None)
		if not t:
			frappe.throw(_("Test not found"))
		if t.status != "Ordered":
			frappe.throw(_("The sample of this test was already collected"))
		sample = "%s-%s" % (self.name, t.idx)
		lr = frappe.get_doc({"doctype": "Lab Result", "lab_order": self.name, "patient": self.patient, "branch": self.branch, "service": t.service, "sample_id": sample})
		lr.insert()
		t.db_set({"status": "Sample Collected", "collected_on": now_datetime(), "sample_id": sample, "result": lr.name})
		self.db_set("status", "In Progress")
		return lr.name

	@frappe.whitelist(methods=["POST"])
	def cancel_order(self):
		self.check_permission("write")
		frappe.has_permission("Lab Order", "write", self, throw=True)
		for t in self.tests:
			if t.status in ("Resulted", "Verified"):
				frappe.throw(_("Test {0} already has a result. The order cannot be cancelled.").format(t.service))
		for t in self.tests:
			if t.charge:
				charges.cancel_charge(t.charge)
			if t.result:
				frappe.delete_doc("Lab Result", t.result, ignore_permissions=True, force=True)
				t.db_set("result", None)
			t.db_set("status", "Cancelled")
		self.db_set("status", "Cancelled")
		return "Cancelled"

	def refresh_status(self):
		rows = frappe.get_all("Lab Order Test", filters={"parent": self.name}, fields=["status", "result"])
		live = [r for r in rows if r.status != "Cancelled"]
		if live and all(r.status == "Verified" for r in live):
			status = "Completed"
		elif any(r.status != "Ordered" for r in live):
			status = "In Progress"
		else:
			status = "Ordered"
		crit = 0
		for r in live:
			if r.result and frappe.db.get_value("Lab Result", r.result, "has_critical"):
				crit = 1
		self.db_set({"status": status, "has_critical": crit})
