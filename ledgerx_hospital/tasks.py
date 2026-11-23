"""Scheduled jobs. Each one is independent and a failure in one record never stops the others."""
import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime, nowdate

from ledgerx_hospital import notify


def _each(rows, fn, label):
	done = 0
	for r in rows:
		try:
			fn(r)
			frappe.db.commit()
			done += 1
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="ledgerx_hospital %s failed for %s" % (label, r))
	return done


def post_bed_days():
	"""Every night: the day just reached is charged for every admitted patient."""
	def one(name):
		frappe.get_doc("Inpatient Admission", name).post_bed_days()
	return _each(frappe.get_all("Inpatient Admission", filters={"status": "Admitted"}, pluck="name"), one, "bed days")


def mark_no_shows():
	"""Appointments of past days still Scheduled become No Show."""
	frappe.db.sql("UPDATE `tabPatient Appointment` SET status = 'No Show' WHERE status = 'Scheduled' AND appointment_date < %s", nowdate())


def expire_approvals():
	frappe.db.sql("""UPDATE `tabInsurance Approval` SET status = 'Expired' WHERE status IN ('Approved', 'Partially Approved') AND valid_till IS NOT NULL AND valid_till < %s""", nowdate())


def miss_overdue_doses():
	"""A dose still Scheduled two hours after its time is recorded as Missed so the ward sees it."""
	frappe.db.sql("UPDATE `tabMedication Administration` SET status = 'Missed' WHERE status = 'Scheduled' AND scheduled_at < %s", add_to_date(now_datetime(), hours=-2))


def refresh_bills():
	"""Payments made in the accounts reach the bills, and the doctor statements waiting for payment."""
	from ledgerx_hospital import billing

	def one(name):
		billing.refresh(name)
	_each(frappe.get_all("Hospital Bill", filters={"docstatus": 1, "status": ["in", ["Unpaid", "Partly Paid", "Credit"]]}, pluck="name"), one, "bill refresh")

	def stmt(name):
		frappe.get_doc("Doctor Statement", name).refresh_status()
	_each(frappe.get_all("Doctor Statement", filters={"status": "Approved", "purchase_invoice": ["is", "set"]}, pluck="name"), stmt, "statement refresh")


def refresh_claims():
	"""Claims follow the money received on their invoices."""
	from ledgerx_hospital import billing

	def one(name):
		c = frappe.get_doc("Insurance Claim", name)
		for ln in c.lines:
			ln.paid_amount = billing.invoice_paid(ln.invoice)
		c.save(ignore_permissions=True)
	_each(frappe.get_all("Insurance Claim", filters={"status": ["in", ["Submitted", "Partially Paid"]]}, pluck="name"), one, "claim refresh")


def overdue_er_alerts():
	"""A waiting emergency patient past the target time gets an alert to the managers once."""
	from ledgerx_hospital.engine import triage

	now = now_datetime()
	rows = frappe.get_all("Emergency Visit", filters={"status": "Waiting", "triage_level": ["in", ["1", "2", "3", "4", "5"]]}, fields=["name", "triage_level", "arrival_time", "branch", "temp_name", "patient"])
	for r in rows:
		if triage.is_overdue(int(r.triage_level), frappe.utils.get_datetime(r.arrival_time), now):
			for u in notify.users_with_role("Hospital Manager"):
				notify.todo(u, "Emergency Visit", r.name, _("Emergency patient {0} (level {1}) is waiting past the target time").format(r.patient or r.temp_name, r.triage_level))


def daily():
	for fn in (post_bed_days, mark_no_shows, expire_approvals, miss_overdue_doses, refresh_bills, refresh_claims):
		try:
			fn()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="ledgerx_hospital daily step failed: %s" % fn.__name__)


def every_fifteen_minutes():
	for fn in (miss_overdue_doses, overdue_er_alerts):
		try:
			fn()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="ledgerx_hospital step failed: %s" % fn.__name__)
