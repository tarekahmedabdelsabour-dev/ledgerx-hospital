import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ledgerx_hospital.engine.slots import to_minutes


class HospitalDoctor(Document):
	def validate(self):
		branches = {b.branch for b in self.branches}
		if self.default_branch and branches and self.default_branch not in branches:
			frappe.throw(_("The default branch must be one of the doctor's branches"))
		spans = {}
		for r in self.schedule:
			a, b = to_minutes(r.from_time), to_minutes(r.to_time)
			if a is None or b is None or b <= a:
				frappe.throw(_("Schedule row {0}: the end time must be after the start time").format(r.idx))
			if not r.slot_minutes or int(r.slot_minutes) <= 0:
				frappe.throw(_("Schedule row {0}: enter the slot length in minutes").format(r.idx))
			if branches and r.branch and r.branch not in branches:
				frappe.throw(_("Schedule row {0}: branch {1} is not one of the doctor's branches").format(r.idx, r.branch))
			for (x, y, i) in spans.get(r.weekday, []):
				if a < y and x < b:
					frappe.throw(_("Schedule rows {0} and {1} overlap on {2}").format(i, r.idx, _(r.weekday)))
			spans.setdefault(r.weekday, []).append((a, b, r.idx))
		for t in self.time_off:
			if t.to_date and t.from_date and t.to_date < t.from_date:
				frappe.throw(_("Time off row {0}: the end date is before the start date").format(t.idx))
		for f in self.fee_rules:
			if flt(f.value) < 0:
				frappe.throw(_("Fee rule row {0}: the value cannot be negative").format(f.idx))
			if f.mode == "Percent" and flt(f.value) > 100:
				frappe.throw(_("Fee rule row {0}: a percentage cannot exceed 100").format(f.idx))
