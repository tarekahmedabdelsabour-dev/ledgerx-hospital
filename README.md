# LedgerX Hospital

A hospital app for LedgerX that scales from one small clinic to a group of hospitals. It adds no parallel accounts or stock: every bill produces real Sales Invoices, every payment a real Payment Entry, every medicine or theatre consumable a real Stock Entry and every doctor payable a real Purchase Invoice, so Accounts, Stock, HR, CRM and Operations Research keep working on hospital data unchanged.

## What it does

- **Branches**: any number of hospitals or clinics, each with its own company, cost center, warehouses, price list and users (a user sees only the branches given to them).
- **Front desk**: patient file (national ID parsed for birth date and gender, allergies, insurance card), appointments built from each doctor's weekly schedule and time off, check-in with a queue number, follow-up visits at a reduced fee.
- **Clinic**: the doctor's visit record with diagnoses, prescriptions, lab, radiology and procedure orders, vital signs with out-of-range highlighting, allergy and duplicate-medicine warnings (warnings only, the doctor decides).
- **Inpatients**: wards and beds, admission, transfer between beds, deposits, nursing notes, medication administration, discharge. Bed days are charged by a configurable cut-off hour.
- **Laboratory and radiology**: orders from the visit, sample collection, result sheets with reference ranges by age and sex, critical value alerts, verification; radiology order, perform, report, verify.
- **Theatre**: operating rooms, booking with room and surgeon conflict checks, pre-op checklist, consumables issued from stock, theatre time, surgeon and team fees.
- **Emergency**: triage levels 1 to 5 with waiting targets, queue board, doctor assignment, disposition or admission.
- **Pharmacy**: dispensing against a prescription, first-expiry-first-out batches, returns.
- **Billing**: every service becomes a charge; a bill collects the unbilled charges, splits each line between the insurer and the patient by the plan rules, and creates the patient's invoice (deposits are applied automatically) and the insurer's invoice.
- **Insurance**: companies and plans with price lists, coverage per service or service type, co-pay, caps and annual limits; prior approvals; claims that follow the insurer's invoices, payments spread oldest first, rejections written off to an account you choose.
- **Doctor fees**: rules per doctor (percentage or fixed, per service or type, cash or insurance), statements with deductions, payable through a Purchase Invoice.
- **Reports**: daily census, bed occupancy, revenue analysis, unbilled charges, insurance receivable with aging, appointments and no-shows, lab turnaround, emergency waiting times, theatre utilisation, branch comparison, medication dispensing, doctor fees due.

## Install

See `docs/INSTALL.md`.

## Honest limits

The calculations (billing split, doctor fees, slots, bed days, lab flags, triage order, claims, first-expiry-first-out) are covered by 43 unit tests. The parts that talk to the database (creating invoices, payments, stock entries; the screens and buttons) were written against the ERPNext v16 source and checked with static scripts, but have not been run on a live site. Run the first-day checklist in `docs/INSTALL.md` on dummy data before any real patient. A hospital app touches clinical and financial records: it supports your staff, it does not replace their judgement, and the warnings it shows are aids, not diagnoses.
