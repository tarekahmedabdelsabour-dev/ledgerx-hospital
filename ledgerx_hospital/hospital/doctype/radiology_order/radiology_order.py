import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from ledgerx_hospital import charges, notify

FLOW = {"Ordered": ["Scheduled", "Performed"], "Scheduled": ["Performed", "Ordered"], "Performed": ["Reported"], "Reported": ["Verified"], "Verified": []}


class RadiologyOrder(Document):
	def validate(self):
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "insurance_plan"], as_dict=1)
		self.patient_name = p.patient_name
		if not self.insurance_plan:
			self.insurance_plan = p.insurance_plan
		self.ordered_on = self.ordered_on or now_datetime()
		if frappe.db.get_value("Hospital Service", self.service, "service_type") != "Radiology":
			frappe.throw(_("{0} is not a radiology service").format(self.service))
		if not self.is_new() and frappe.db.get_value("Radiology Order", self.name, "status") == "Verified" and not self.flags.allow_verified_edit:
			frappe.throw(_("The report is verified and locked"))

	def after_insert(self):
		self.db_set("charge", charges.add_charge(self.patient, self.branch, service=self.service, doctor=self.ordering_doctor, source_doctype="Radiology Order", source_name=self.name,
			admission=self.admission, encounter=self.encounter, insurance_plan=self.insurance_plan))

	def move(self, to):
		if to not in FLOW.get(self.status, []):
			frappe.throw(_("The order cannot go from {0} to {1}").format(_(self.status), _(to)))
		self.status = to

	@frappe.whitelist(methods=["POST"])
	def schedule(self, at):
		self.check_permission("write")
		frappe.has_permission("Radiology Order", "write", self, throw=True)
		self.move("Scheduled")
		self.scheduled_at = at
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def perform(self, technician=None):
		self.check_permission("write")
		frappe.has_permission("Radiology Order", "write", self, throw=True)
		self.move("Performed")
		self.performed_on = now_datetime()
		self.technician = technician or frappe.utils.get_fullname(frappe.session.user)
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def report(self, findings, impression, critical=0):
		self.check_permission("write")
		frappe.has_permission("Radiology Order", "write", self, throw=True)
		if not (findings and impression):
			frappe.throw(_("Enter the findings and the impression"))
		self.move("Reported")
		self.findings, self.impression, self.critical = findings, impression, 1 if int(critical or 0) else 0
		self.radiologist = frappe.db.get_value("Hospital Doctor", {"user": frappe.session.user}, "name") or self.radiologist
		self.save()
		if self.critical:
			notify.todo(frappe.db.get_value("Hospital Doctor", self.ordering_doctor, "user"), "Radiology Order", self.name,
				_("Critical imaging finding for {0}: {1}").format(self.patient_name, self.impression))
		return self.status

	@frappe.whitelist(methods=["POST"])
	def verify(self):
		self.check_permission("write")
		frappe.has_permission("Radiology Order", "write", self, throw=True)
		self.move("Verified")
		self.verified_on = now_datetime()
		self.flags.allow_verified_edit = True
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def cancel_order(self):
		self.check_permission("write")
		frappe.has_permission("Radiology Order", "write", self, throw=True)
		if self.status not in ("Ordered", "Scheduled"):
			frappe.throw(_("A performed study cannot be cancelled"))
		charges.cancel_charge(self.charge)
		self.status = "Cancelled"
		self.save()
		return self.status
