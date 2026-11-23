"""Thin public wrappers used by the desk screens."""
import frappe

from ledgerx_hospital.hospital.doctype.patient_appointment.patient_appointment import free_slots


@frappe.whitelist()
def free_slots_for(doctor, date, branch=None, exclude=None):
	return free_slots(doctor, date, branch, exclude)
