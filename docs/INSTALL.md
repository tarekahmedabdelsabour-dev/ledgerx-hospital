# Install and first-day checklist

## Install (new app)

```bash
cd ~/frappe-bench-v16
git clone <repository-url> apps/ledgerx_hospital
printf '\nledgerx_hospital\n' >> sites/apps.txt
./env/bin/pip install -e apps/ledgerx_hospital
ln -sfn ~/frappe-bench-v16/apps/ledgerx_hospital/ledgerx_hospital/public sites/assets/ledgerx_hospital
bench --site mysite.localhost install-app ledgerx_hospital
bench --site mysite.localhost migrate
bench --site mysite.localhost clear-cache
```

Then restart everything, and press Ctrl+Shift+R in the browser. The **Hospital** tile appears on the desktop (`/desk/hospital`).

## Set up once

1. **Hospital Settings**: company, price list, the account for rejected claims (optional), the doctor fee item and expense account (created for you), bed cut-off hour, follow-up days and fee percentage.
2. **Hospital Branch**: company, cost center, pharmacy warehouse, theatre warehouse, price list. Give each user the branch through User Permissions.
3. **Hospital Department**, **Ward**, **Hospital Bed** (each bed points at a bed-day service), **Operating Room** (optional hourly service).
4. **Hospital Service**: consultations, procedures, lab tests, radiology, surgeries, bed days. Each creates its Item and price. A **Lab Test Template** (same name as the lab service) holds the parameters and reference ranges.
5. **Hospital Doctor**: user, supplier (to pay fees), branches, weekly schedule, fee rules.
6. Insurance: **Hospital Insurer** (its customer account is created for you), **Hospital Insurance Plan** with its rules.
7. Medicines: normal Items with batch and expiry tracking, and a selling price.

## First-day checklist (use dummy data)

1. Register a patient with a valid national ID; check the birth date and gender are filled.
2. Book an appointment, check in, start the visit, add a diagnosis, a lab test and a medicine, complete the visit.
3. Collect the sample, enter the result, mark resulted, verify; open the Hospital Charge list and see the charges.
4. Dispense the medicine: check the Stock Entry and the batch.
5. Create a bill: **Get Unbilled Charges**, check the insurer and patient shares, submit; open both Sales Invoices.
6. Receive a payment; check the Payment Entry and the bill status.
7. Admit a patient, receive a deposit, transfer bed, discharge; check the bed-day charges and that the deposit is applied to the invoice.
8. Make an insurance claim from the insurer's bills, send it, register a payment, record a rejection.
9. Make a doctor statement, approve it, create the payable.
10. Cancel a bill and check the charges return to Unbilled.

## Notes

- Service items must carry the codes your tax authority expects if you use electronic invoicing.
- A rejected claim is written off only when the write-off account is set in Hospital Settings.
- Update: `cd ~/frappe-bench-v16/apps/ledgerx_hospital && git pull origin main`, then migrate and restart.
