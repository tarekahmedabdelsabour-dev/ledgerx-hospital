import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, get_datetime, now_datetime

from ledgerx_hospital import charges, data, stock_ops
from ledgerx_hospital.engine import or_schedule


class SurgeryBooking(Document):
	def people(self):
		ids = [self.surgeon] + [t.doctor for t in self.team]
		return [i for i in ids if i]

	def validate(self):
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "insurance_plan", "status"], as_dict=1)
		self.patient_name = p.patient_name
		if p.status == "Deceased":
			frappe.throw(_("The patient is marked deceased"))
		self.insurance_plan = self.insurance_plan or p.insurance_plan
		if frappe.db.get_value("Hospital Service", self.service, "service_type") != "Surgery":
			frappe.throw(_("{0} is not a surgery service").format(self.service))
		room = frappe.db.get_value("Operating Room", self.operating_room, ["branch", "status"], as_dict=1)
		if room.branch != self.branch:
			frappe.throw(_("The operating room belongs to another branch"))
		if room.status == "Maintenance":
			frappe.throw(_("The operating room is under maintenance"))
		if self.admission and frappe.db.get_value("Inpatient Admission", self.admission, "patient") != self.patient:
			frappe.throw(_("The admission belongs to another patient"))
		if cint(self.expected_minutes) <= 0:
			frappe.throw(_("Enter the expected duration in minutes"))
		start = get_datetime(self.scheduled_start)
		if self.is_new() and start < now_datetime() and self.status == "Booked":
			frappe.throw(_("The scheduled time is in the past"))
		self.scheduled_end = or_schedule.case_end(start, self.expected_minutes)
		docs = [t.doctor for t in self.team]
		if len(docs) != len(set(docs)) or self.surgeon in docs:
			frappe.throw(_("A doctor appears twice in the surgical team"))
		if self.status in ("Booked", "Pre-op Ready", "In Progress"):
			self.check_conflicts(start)
		if self.is_new() and not self.preop:
			for r in data.settings().preop:
				self.append("preop", {"check_item": r.check_item})
		for r in self.preop:
			if cint(r.done) and not r.done_on:
				r.done_by, r.done_on = frappe.session.user, now_datetime()
			if not cint(r.done):
				r.done_by = r.done_on = None
		for c in self.consumables:
			info = data.item_info(c.item_code)
			if not info.is_stock_item:
				frappe.throw(_("Consumable row {0}: {1} is not a stock item").format(c.idx, c.item_code))
			c.item_name = info.item_name
			price, _src = data.item_price(c.item_code, self.insurance_plan or None, self.branch, start)
			c.rate = flt(price)
			c.amount = round(flt(c.qty) * c.rate, 2)

	def check_conflicts(self, start):
		buf = cint(data.settings().or_buffer_minutes)
		rows = frappe.get_all("Surgery Booking", filters={"status": ["in", ["Booked", "Pre-op Ready", "In Progress"]], "name": ["!=", self.name or ""], "branch": self.branch,
			"scheduled_start": ["between", [add_days(start, -2), add_days(start, 2)]]}, fields=["name", "scheduled_start", "scheduled_end", "operating_room", "surgeon"])
		existing = []
		for r in rows:
			team = frappe.get_all("Surgery Team", filters={"parent": r.name}, pluck="doctor")
			existing.append({"name": r.name, "start": get_datetime(r.scheduled_start), "end": get_datetime(r.scheduled_end), "room": r.operating_room, "people": [r.surgeon] + team})
		new = {"name": self.name, "start": start, "end": get_datetime(self.scheduled_end), "room": self.operating_room, "people": self.people()}
		found = or_schedule.conflicts(new, existing, buf)
		if found:
			name, what = found[0]
			who = _("the operating room") if what == "room" else _("doctor {0}").format(frappe.db.get_value("Hospital Doctor", what, "doctor_name"))
			frappe.throw(_("Conflict with booking {0}: {1} is already booked at that time.").format(name, who))

	def preop_complete(self):
		return all(cint(r.done) for r in self.preop)

	@frappe.whitelist(methods=["POST"])
	def mark_ready(self):
		self.check_permission("write")
		frappe.has_permission("Surgery Booking", "write", self, throw=True)
		if self.status != "Booked":
			frappe.throw(_("The booking is not waiting for pre-op checks"))
		if not self.preop_complete():
			frappe.throw(_("Finish the pre-op checklist first"))
		self.status = "Pre-op Ready"
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def start(self, emergency=0):
		self.check_permission("write")
		frappe.has_permission("Surgery Booking", "write", self, throw=True)
		if self.status not in ("Booked", "Pre-op Ready"):
			frappe.throw(_("The case cannot start from status {0}").format(_(self.status)))
		if not cint(emergency) and not self.preop_complete():
			frappe.throw(_("The pre-op checklist is not complete. Tick it, or start as an emergency case."))
		self.status, self.actual_start = "In Progress", now_datetime()
		self.save()
		return self.status

	@frappe.whitelist(methods=["POST"])
	def complete(self, operation_notes=None, complications=None):
		self.check_permission("write")
		frappe.has_permission("Surgery Booking", "write", self, throw=True)
		if self.status != "In Progress":
			frappe.throw(_("The case has not started"))
		self.actual_end = now_datetime()
		self.operation_notes = operation_notes or self.operation_notes
		self.complications = complications or self.complications
		if not self.operation_notes:
			frappe.throw(_("Write the operation notes"))
		self.issue_consumables()
		self.post_charges()
		self.status = "Completed"
		self.save()
		return self.status

	def issue_consumables(self):
		if self.stock_entry or not self.consumables:
			return
		b = data.branch_doc(self.branch)
		wh = b.or_warehouse or b.warehouse
		if not wh:
			frappe.throw(_("Set a theatre warehouse on branch {0}").format(self.branch))
		lines = [{"item_code": c.item_code, "qty": c.qty, "label": c.item_name} for c in self.consumables]
		plan, short = stock_ops.allocate(wh, lines, self.actual_end, 0)
		if short:
			frappe.throw(_("Not enough stock in {0}: {1}").format(wh, "; ".join(short)))
		se = stock_ops.issue(b.company, wh, b.cost_center, plan, str(self.actual_end)[:10], _("Surgery {0}").format(self.name))
		for c, (ln, alloc) in zip(self.consumables, plan):
			c.batches = ", ".join("%s x %s" % (bn, q) if bn else str(q) for bn, q in alloc)
		self.stock_entry = se.name

	def post_charges(self):
		common = {"patient": self.patient, "branch": self.branch, "admission": self.admission, "insurance_plan": self.insurance_plan, "posting_date": str(self.actual_end)[:10]}
		self.procedure_charge = charges.add_charge(service=self.service, doctor=self.surgeon, source_doctype="Surgery Booking", source_name=self.name, **common)
		for t in self.team:
			if t.service and not t.charge:
				t.charge = charges.add_charge(service=t.service, doctor=t.doctor, source_doctype="Surgery Team", source_name="%s/%s" % (self.name, t.idx), **common)
		hs = frappe.db.get_value("Operating Room", self.operating_room, "hourly_service")
		if hs:
			hours = max((get_datetime(self.actual_end) - get_datetime(self.actual_start)).total_seconds() / 3600.0, 0.25)
			self.theatre_charge = charges.add_charge(service=hs, qty=round(hours, 2), source_doctype="Surgery Theatre", source_name=self.name, **common)
		for c in self.consumables:
			if not c.charge and flt(c.qty) > 0:
				c.charge = charges.add_charge(item_code=c.item_code, qty=c.qty, rate=c.rate, source_doctype="Surgery Consumable", source_name="%s/%s" % (self.name, c.idx), **common)

	@frappe.whitelist(methods=["POST"])
	def cancel_booking(self, reason):
		self.check_permission("write")
		frappe.has_permission("Surgery Booking", "write", self, throw=True)
		if self.status not in ("Booked", "Pre-op Ready"):
			frappe.throw(_("A case that started cannot be cancelled"))
		if not reason:
			frappe.throw(_("Enter the reason"))
		self.status = "Cancelled"
		self.operation_notes = _("Cancelled: {0}").format(reason)
		self.save()
		return self.status
