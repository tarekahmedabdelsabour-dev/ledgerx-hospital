import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from ledgerx_hospital import notify
from ledgerx_hospital.engine import lab, people


def _range_text(r):
	if not r:
		return ""
	if r.get("text_range"):
		return r["text_range"]
	lo, hi = r.get("low"), r.get("high")
	if lo not in (None, "") and hi not in (None, ""):
		return "%g - %g" % (lo, hi)
	if lo not in (None, ""):
		return ">= %g" % lo
	if hi not in (None, ""):
		return "<= %g" % hi
	return ""


class LabResult(Document):
	def patient_context(self):
		p = frappe.db.get_value("Hospital Patient", self.patient, ["gender", "date_of_birth", "patient_name"], as_dict=1)
		age = people.age_years(getdate(p.date_of_birth)) if p.date_of_birth else None
		return p.patient_name, p.gender, age

	def template_ranges(self):
		t = frappe.get_cached_doc("Lab Test Template", self.service)
		out = {}
		for r in t.ranges:
			out.setdefault(r.parameter, []).append({k: r.get(k) for k in ("gender", "age_from", "age_to", "low", "high", "crit_low", "crit_high", "text_range")})
		return t, out

	def before_insert(self):
		name, gender, age = self.patient_context()
		self.patient_name = name
		t, ranges = self.template_ranges()
		if not self.result_values:
			for p in t.parameters:
				rng = lab.pick_range(ranges.get(p.parameter), gender, age)
				self.append("result_values", {"parameter": p.parameter, "unit": p.unit, "result_type": p.result_type, "reference": _range_text(rng)})

	def validate(self):
		if not self.is_new() and frappe.db.get_value("Lab Result", self.name, "status") == "Verified" and not self.flags.allow_verified_edit:
			frappe.throw(_("The result is verified and locked"))
		name, gender, age = self.patient_context()
		self.patient_name = name
		_t, ranges = self.template_ranges()
		crit = 0
		for r in self.result_values:
			r.value = (r.value or "").strip()
			rng = lab.pick_range(ranges.get(r.parameter), gender, age)
			r.reference = _range_text(rng) or r.reference
			r.flag = ""
			if r.value and r.result_type == "Numeric":
				num, _op = lab.parse_number(r.value)
				if num is None:
					frappe.throw(_("Row {0}: {1} must be a number (for example 5.2 or <0.5)").format(r.idx, r.parameter))
				r.flag = lab.flag_text(r.value, rng)
			if lab.is_critical(r.flag):
				crit = 1
		self.has_critical = crit

	def _require_values(self):
		missing = [r.parameter for r in self.result_values if not r.value]
		if missing:
			frappe.throw(_("Enter a value for: {0}").format(", ".join(missing)))

	def _sync_order(self, status):
		order = frappe.get_doc("Lab Order", self.lab_order)
		row = next((t for t in order.tests if t.result == self.name), None)
		if row:
			row.db_set("status", status)
		order.refresh_status()
		return order

	@frappe.whitelist(methods=["POST"])
	def mark_resulted(self):
		self.check_permission("write")
		frappe.has_permission("Lab Result", "write", self, throw=True)
		if self.status != "Draft":
			frappe.throw(_("The result was already entered"))
		self._require_values()
		self.status, self.resulted_on, self.resulted_by = "Resulted", now_datetime(), frappe.session.user
		self.save()
		order = self._sync_order("Resulted")
		if self.has_critical:
			bad = ", ".join("%s %s" % (r.parameter, r.flag) for r in self.result_values if lab.is_critical(r.flag or ""))
			notify.todo(frappe.db.get_value("Hospital Doctor", order.ordering_doctor, "user"), "Lab Result", self.name,
				_("Critical lab result for {0}: {1}").format(self.patient_name, bad))
		return self.status

	@frappe.whitelist(methods=["POST"])
	def verify(self):
		self.check_permission("write")
		frappe.has_permission("Lab Result", "write", self, throw=True)
		if self.status != "Resulted":
			frappe.throw(_("Enter and save the result first"))
		self.status, self.verified_on, self.verified_by = "Verified", now_datetime(), frappe.session.user
		self.flags.allow_verified_edit = True
		self.save()
		self._sync_order("Verified")
		return self.status
