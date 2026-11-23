import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ledgerx_hospital import charges, data, stock_ops
from ledgerx_hospital.engine import safety
from ledgerx_hospital.engine.money import cents, money


def returned_qty(dispense, item_code):
	return flt(frappe.db.sql("""SELECT COALESCE(SUM(l.qty), 0) FROM `tabDispense Line` l INNER JOIN `tabMedication Dispense` d ON d.name = l.parent
		WHERE d.docstatus = 1 AND d.is_return = 1 AND d.return_against = %s AND l.item_code = %s""", (dispense, item_code))[0][0])


class MedicationDispense(Document):
	def validate(self):
		p = frappe.db.get_value("Hospital Patient", self.patient, ["patient_name", "allergies", "insurance_plan"], as_dict=1)
		self.patient_name = p.patient_name
		self.insurance_plan = self.insurance_plan or p.insurance_plan
		b = data.branch_doc(self.branch)
		self.warehouse = self.warehouse or b.warehouse
		if not self.warehouse:
			frappe.throw(_("Set a pharmacy warehouse on branch {0}").format(self.branch))
		if frappe.db.get_value("Warehouse", self.warehouse, "company") != b.company:
			frappe.throw(_("The warehouse belongs to another company"))
		if not self.items:
			frappe.throw(_("Add at least one medicine"))
		drugs = []
		for l in self.items:
			info = data.item_info(l.item_code)
			if not info.is_stock_item or info.disabled:
				frappe.throw(_("Row {0}: {1} is not an active stock item").format(l.idx, l.item_code))
			if flt(l.qty) <= 0:
				frappe.throw(_("Row {0}: the quantity must be more than zero").format(l.idx))
			l.item_name, l.uom = info.item_name, info.stock_uom
			price, _src = data.item_price(l.item_code, self.insurance_plan or None, self.branch, self.posting_date)
			if price is None:
				frappe.throw(_("Row {0}: {1} has no selling price").format(l.idx, l.item_code))
			l.rate = flt(price)
			l.amount = round(flt(l.qty) * l.rate, 2)
			drugs.append({"item": l.item_code, "name": info.item_name, "ingredient": data.ingredient_of(l.item_code)})
		self.total = money(sum(cents(l.amount) for l in self.items))
		if not self.is_return:
			notes = ["%s: %s" % (_("Possible allergy"), h["allergy"] + " / " + h["item"]) for h in safety.allergy_hits(p.allergies, drugs)]
			self.safety_notes = "\n".join(notes)
			if notes:
				frappe.msgprint("<br>".join(notes), title=_("Check before dispensing"), indicator="orange")
		else:
			self.check_return()

	def check_return(self):
		if not self.return_against:
			frappe.throw(_("Choose the dispense this return is against"))
		orig = frappe.db.get_value("Medication Dispense", self.return_against, ["docstatus", "patient", "is_return"], as_dict=1)
		if not orig or orig.docstatus != 1 or orig.is_return or orig.patient != self.patient:
			frappe.throw(_("The original dispense must be a submitted dispense of the same patient"))
		sold = {}
		for r in frappe.get_all("Dispense Line", filters={"parent": self.return_against}, fields=["item_code", "qty"]):
			sold[r.item_code] = sold.get(r.item_code, 0) + flt(r.qty)
		ask = {}
		for l in self.items:
			ask[l.item_code] = ask.get(l.item_code, 0) + flt(l.qty)
		for code, q in ask.items():
			left = sold.get(code, 0) - returned_qty(self.return_against, code)
			if q > left + 1e-9:
				frappe.throw(_("{0}: only {1} can still be returned").format(code, left))

	def on_submit(self):
		if self.is_return:
			self.do_return()
		else:
			self.do_dispense()

	def do_dispense(self):
		b = data.branch_doc(self.branch)
		plan, short = stock_ops.allocate(self.warehouse, [{"item_code": l.item_code, "qty": l.qty, "label": l.item_name} for l in self.items], self.posting_date, 0)
		if short:
			frappe.throw(_("Not enough usable stock in {0}: {1}").format(self.warehouse, "; ".join(short)))
		se = stock_ops.issue(b.company, self.warehouse, b.cost_center, plan, self.posting_date, _("Dispense {0}").format(self.name))
		self.db_set("stock_entry", se.name)
		for l, (_ln, alloc) in zip(self.items, plan):
			l.db_set("batches", ", ".join("%s x %s" % (bn, q) if bn else str(q) for bn, q in alloc))
			c = charges.add_charge(self.patient, self.branch, item_code=l.item_code, qty=l.qty, rate=l.rate, description=l.item_name, doctor=self.doctor, source_doctype="Dispense Line",
				source_name=l.name, admission=self.admission, encounter=self.encounter, insurance_plan=self.insurance_plan, posting_date=self.posting_date)
			l.db_set("charge", c)
			if l.prescription_row:
				frappe.db.set_value("Encounter Prescription", l.prescription_row, "dispensed", 1, update_modified=False)

	def do_return(self):
		b = data.branch_doc(self.branch)
		orig = frappe.get_doc("Medication Dispense", self.return_against)
		for l in self.items:
			src = next((x for x in orig.items if x.item_code == l.item_code and x.charge), None)
			st = frappe.db.get_value("Hospital Charge", src.charge, ["status", "qty", "rate", "discount_pct"], as_dict=1) if src else None
			if st and st.status == "Billed":
				frappe.throw(_("{0} was already billed. Cancel the bill first, then return the medicine.").format(l.item_code))
		rows = []
		for l in self.items:
			left = flt(l.qty)
			for r in frappe.db.sql("""SELECT sed.batch_no, sed.qty, sed.basic_rate FROM `tabStock Entry Detail` sed WHERE sed.parent = %s AND sed.item_code = %s ORDER BY sed.idx""",
					(orig.stock_entry, l.item_code), as_dict=1):
				if left <= 1e-9:
					break
				take = min(left, flt(r.qty))
				rows.append({"item_code": l.item_code, "qty": take, "batch_no": r.batch_no, "basic_rate": flt(r.basic_rate)})
				left -= take
			if left > 1e-6:
				frappe.throw(_("{0}: more than the stock issued by the original dispense").format(l.item_code))
		se = stock_ops.receive(b.company, self.warehouse, b.cost_center, rows, self.posting_date, _("Return {0}").format(self.name))
		self.db_set("stock_entry", se.name)
		for l in self.items:
			src = next((x for x in orig.items if x.item_code == l.item_code and x.charge), None)
			if not src:
				continue
			ch = frappe.get_doc("Hospital Charge", src.charge)
			if ch.status == "Cancelled":
				continue
			left = flt(ch.qty) - flt(l.qty)
			if left <= 1e-9:
				charges.cancel_charge(ch.name)
			else:
				ch.qty = left
				ch.save(ignore_permissions=True)

	def before_cancel(self):
		if self.is_return:
			frappe.throw(_("A return cannot be cancelled. Dispense the medicine again instead."))
		if frappe.db.exists("Medication Dispense", {"return_against": self.name, "docstatus": 1}):
			frappe.throw(_("The dispense has returns. Cancel nothing: the returns are part of its history."))

	def on_cancel(self):
		for l in self.items:
			if l.charge:
				charges.cancel_charge(l.charge)
			if l.prescription_row:
				frappe.db.set_value("Encounter Prescription", l.prescription_row, "dispensed", 0, update_modified=False)
		stock_ops.cancel_entry(self.stock_entry)
