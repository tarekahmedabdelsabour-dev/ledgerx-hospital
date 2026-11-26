import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from ledgerx_hospital import charges, data
from ledgerx_hospital.engine import safety


class PatientEncounter(Document):
	def validate(self):
		if not self.is_new() and frappe.db.get_value("Patient Encounter", self.name, "status") == "Completed" and not self.flags.allow_completed_edit:
			frappe.throw(_("The visit is completed and locked. Create a new visit for new findings."))
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "allergies", "insurance_plan", "status"], as_dict=1)
		self.patient_name = p.patient_name
		if p.status == "Deceased":
			frappe.throw(_("The patient is marked deceased"))
		if not self.insurance_plan:
			self.insurance_plan = p.insurance_plan
		if self.admission and frappe.db.get_value("Inpatient Admission", self.admission, "patient") != self.patient:
			frappe.throw(_("The admission belongs to another patient"))
		if self.doctor and not frappe.db.get_value("Hospital Doctor", self.doctor, "active"):
			frappe.throw(_("The doctor is not active"))
		drugs = []
		for r in self.prescriptions:
			info = data.item_info(r.item_code)
			r.drug_name = info.item_name
			drugs.append({"item": r.item_code, "name": info.item_name, "ingredient": data.ingredient_of(r.item_code)})
		notes = []
		for h in safety.allergy_hits(p.allergies, drugs):
			notes.append(_("Possible allergy: the patient is recorded allergic to {0}; check {1}.").format(h["allergy"], h["item"]))
		for a, b in safety.duplicates(drugs):
			notes.append(_("Possible duplicate: {0} and {1} are the same medicine or ingredient.").format(a, b))
		self.safety_notes = "\n".join(notes)
		if notes:
			frappe.msgprint("<br>".join(notes), title=_("Check the prescription"), indicator="orange")

	@frappe.whitelist(methods=["POST"])
	def complete(self):
		self.check_permission("write")
		frappe.has_permission("Patient Encounter", "write", self, throw=True)
		if self.status != "Open":
			frappe.throw(_("The visit is not open"))
		if self.encounter_type == "Outpatient" and not self.diagnoses:
			frappe.throw(_("Add at least one diagnosis before completing the visit"))
		self.make_lab_order()
		for r in self.radiology:
			if not r.radiology_order:
				ro = frappe.get_doc({"doctype": "Radiology Order", "patient": self.patient, "branch": self.branch, "ordering_doctor": self.doctor, "service": r.service,
					"body_part": r.body_part, "clinical_info": r.clinical_info or self.chief_complaint, "encounter": self.name, "admission": self.admission, "insurance_plan": self.insurance_plan})
				ro.insert(ignore_permissions=True)
				r.db_set("radiology_order", ro.name)
		for r in self.procedures:
			if not r.charge:
				r.db_set("charge", charges.add_charge(self.patient, self.branch, service=r.service, qty=r.qty or 1, doctor=self.doctor, source_doctype="Encounter Procedure", source_name=r.name,
					admission=self.admission, encounter=self.name, insurance_plan=self.insurance_plan))
		self.status, self.completed_on = "Completed", now_datetime()
		self.flags.allow_completed_edit = True
		self.save()
		if self.appointment:
			frappe.db.set_value("Patient Appointment", self.appointment, "status", "Completed")
		return self.status

	def make_lab_order(self):
		rows = [r for r in self.lab_tests if not r.lab_order]
		if not rows:
			return
		lo = frappe.get_doc({"doctype": "Lab Order", "patient": self.patient, "branch": self.branch, "ordering_doctor": self.doctor, "encounter": self.name, "admission": self.admission,
			"insurance_plan": self.insurance_plan, "priority": "Urgent" if any(cint(r.urgent) for r in rows) else "Routine", "clinical_info": self.chief_complaint,
			"tests": [{"service": r.service} for r in rows]})
		lo.insert(ignore_permissions=True)
		for r in rows:
			r.db_set("lab_order", lo.name)

	@frappe.whitelist(methods=["POST"])
	def cancel_visit(self):
		self.check_permission("write")
		frappe.has_permission("Patient Encounter", "write", self, throw=True)
		if self.status == "Completed":
			frappe.throw(_("A completed visit cannot be cancelled"))
		self.status = "Cancelled"
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def prescription_to_dispense(self):
		"""Values for a new Medication Dispense with the prescribed medicines that are not dispensed yet."""
		self.check_permission("write")
		items = [{"item_code": r.item_code, "qty": r.qty or 1, "prescription_row": r.name} for r in self.prescriptions if not cint(r.dispensed)]
		if not items:
			frappe.throw(_("Every prescribed medicine was already dispensed"))
		return {"patient": self.patient, "branch": self.branch, "encounter": self.name, "admission": self.admission, "doctor": self.doctor, "insurance_plan": self.insurance_plan, "items": items}
