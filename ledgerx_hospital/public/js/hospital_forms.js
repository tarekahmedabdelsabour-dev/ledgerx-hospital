// Buttons and small dialogs of the Hospital screens. Every action calls a server method that re-checks permissions and rules.
(function () {
	const run = (frm, method, args, done) =>
		frm.call({ doc: frm.doc, method, args: args || {}, freeze: true }).then((r) => {
			if (done) done(r);
			return frm.reload_doc();
		});

	const prompt = (title, fields, primary, cb) => {
		frappe.prompt(fields, (v) => cb(v), title, primary);
	};

	const group = __("Actions");
	const btn = (frm, label, fn, grp) => frm.add_custom_button(label, fn, grp === undefined ? group : grp);

	const newDoc = (doctype, values) => frappe.new_doc(doctype, values || {});

	// ---------------------------------------------------------------- patient
	frappe.ui.form.on("Hospital Patient", {
		refresh(frm) {
			if (frm.is_new()) return;
			frappe.call({ method: "ledgerx_hospital.api.patient_summary", args: { patient: frm.doc.name } }).then((r) => {
				const s = r.message;
				if (!s) return;
				const bits = [];
				if (s.patient.allergies) bits.push(`<b style="color:var(--red-600)">${__("Allergies")}:</b> ${frappe.utils.escape_html(s.patient.allergies)}`);
				if (s.admission) bits.push(`${__("In hospital")}: ${s.admission.ward || ""} / ${s.admission.bed || ""}`);
				if (s.unbilled_count) bits.push(`${__("Unbilled")}: ${s.unbilled_count} (${format_currency(s.unbilled_total)})`);
				if (s.patient_owes > 0) bits.push(`${__("Patient owes")}: ${format_currency(s.patient_owes)}`);
				if (bits.length) frm.dashboard.add_comment(bits.join(" &nbsp;|&nbsp; "), s.patient.allergies ? "red" : "blue", true);
			});
			const v = { patient: frm.doc.name, branch: frm.doc.branch, insurance_plan: frm.doc.insurance_plan };
			btn(frm, __("Appointment"), () => newDoc("Patient Appointment", v), __("Create"));
			btn(frm, __("Emergency Visit"), () => newDoc("Emergency Visit", { patient: frm.doc.name, branch: frm.doc.branch, insurance_plan: frm.doc.insurance_plan }), __("Create"));
			btn(frm, __("Admission"), () => newDoc("Inpatient Admission", v), __("Create"));
			btn(frm, __("Vital Signs"), () => newDoc("Vital Signs", { patient: frm.doc.name, branch: frm.doc.branch }), __("Create"));
			btn(frm, __("Bill"), () => newDoc("Hospital Bill", v), __("Create"));
		},
	});

	// ---------------------------------------------------------------- appointment
	frappe.ui.form.on("Patient Appointment", {
		refresh(frm) {
			if (frm.is_new()) {
				if (frm.doc.doctor && frm.doc.appointment_date) btn(frm, __("Pick a Free Slot"), () => pickSlot(frm), null);
				return;
			}
			if (frm.doc.status === "Scheduled") {
				btn(frm, __("Check In"), () => run(frm, "check_in"), null);
				btn(frm, __("Cancel Appointment"), () => prompt(__("Cancel Appointment"), [{ fieldname: "reason", label: __("Reason"), fieldtype: "Data", reqd: 1 }], __("Cancel Appointment"), (v) => run(frm, "cancel_appointment", { reason: v.reason })), null);
			}
			if (["Checked In", "In Consultation"].includes(frm.doc.status)) {
				btn(frm, frm.doc.encounter ? __("Open Visit") : __("Start Visit"), () =>
					frm.doc.encounter ? frappe.set_route("Form", "Patient Encounter", frm.doc.encounter) : frm.call({ doc: frm.doc, method: "start_encounter" }).then((r) => frappe.set_route("Form", "Patient Encounter", r.message)), null);
			}
		},
		doctor(frm) { if (frm.doc.doctor && frm.doc.appointment_date && frm.is_new()) pickSlot(frm); },
		appointment_date(frm) { if (frm.doc.doctor && frm.doc.appointment_date && frm.is_new()) pickSlot(frm); },
	});

	function pickSlot(frm) {
		frappe.call({ method: "ledgerx_hospital.appointments.free_slots_for", args: { doctor: frm.doc.doctor, date: frm.doc.appointment_date, branch: frm.doc.branch, exclude: frm.doc.name } })
			.then((r) => {
				const slots = r.message || [];
				if (!slots.length) return frappe.show_alert({ message: __("No free slots on this day"), indicator: "orange" });
				prompt(__("Free Slots"), [{ fieldname: "slot", label: __("Time"), fieldtype: "Select", options: slots.map((s) => s.from), reqd: 1 }], __("Use this time"), (v) => frm.set_value("from_time", v.slot + ":00"));
			});
	}

	// ---------------------------------------------------------------- encounter
	frappe.ui.form.on("Patient Encounter", {
		refresh(frm) {
			if (frm.is_new()) return;
			if (frm.doc.status === "Open") {
				btn(frm, __("Complete Visit"), () => frappe.confirm(__("Complete the visit? Lab, radiology and procedure orders are sent and the visit is locked."), () => run(frm, "complete")), null);
			}
			if (frm.doc.prescriptions && frm.doc.prescriptions.length) {
				btn(frm, __("Dispense Medicines"), () => frm.call({ doc: frm.doc, method: "prescription_to_dispense" }).then((r) => r.message && newDoc("Medication Dispense", r.message)), __("Create"));
			}
			btn(frm, __("Vital Signs"), () => newDoc("Vital Signs", { patient: frm.doc.patient, branch: frm.doc.branch, encounter: frm.doc.name }), __("Create"));
			if (frm.doc.safety_notes) frm.dashboard.add_comment(frappe.utils.escape_html(frm.doc.safety_notes).replace(/\n/g, "<br>"), "orange", true);
		},
	});

	// ---------------------------------------------------------------- admission
	frappe.ui.form.on("Inpatient Admission", {
		refresh(frm) {
			frm.set_query("bed", () => ({ filters: { branch: frm.doc.branch, status: "Available", active: 1 } }));
			if (frm.is_new() || frm.doc.status !== "Admitted") return;
			btn(frm, __("Transfer to Another Bed"), () => prompt(__("Transfer"), [{ fieldname: "bed", label: __("Bed"), fieldtype: "Link", options: "Hospital Bed", reqd: 1,
				get_query: () => ({ filters: { branch: frm.doc.branch, status: "Available", active: 1 } }) }], __("Transfer"), (v) => run(frm, "transfer", { bed: v.bed })));
			btn(frm, __("Receive Deposit"), () => prompt(__("Deposit"), [{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1 }, { fieldname: "mode_of_payment", label: __("Mode of Payment"), fieldtype: "Link", options: "Mode of Payment", reqd: 1 },
				{ fieldname: "reference_no", label: __("Reference"), fieldtype: "Data" }], __("Receive"), (v) => run(frm, "add_deposit", v)));
			btn(frm, __("Discharge"), () => prompt(__("Discharge"), [{ fieldname: "discharge_type", label: __("Discharge Type"), fieldtype: "Select", options: "\nRecovered\nImproved\nReferred\nAgainst Medical Advice\nDeceased", reqd: 1 },
				{ fieldname: "summary", label: __("Discharge Summary"), fieldtype: "Text" }], __("Discharge"), (v) => run(frm, "discharge", v)));
			btn(frm, __("Nursing Note"), () => newDoc("Nursing Note", { admission: frm.doc.name }), __("Create"));
			btn(frm, __("Medication Dose"), () => newDoc("Medication Administration", { admission: frm.doc.name }), __("Create"));
			btn(frm, __("Surgery"), () => newDoc("Surgery Booking", { patient: frm.doc.patient, branch: frm.doc.branch, admission: frm.doc.name, insurance_plan: frm.doc.insurance_plan }), __("Create"));
			btn(frm, __("Bill"), () => newDoc("Hospital Bill", { patient: frm.doc.patient, branch: frm.doc.branch, admission: frm.doc.name, insurance_plan: frm.doc.insurance_plan }), __("Create"));
		},
	});
	frappe.ui.form.on("Medication Administration", {
		refresh(frm) {
			if (frm.is_new() || frm.doc.status !== "Scheduled") return;
			btn(frm, __("Given"), () => run(frm, "give"), null);
			btn(frm, __("Held"), () => prompt(__("Held"), [{ fieldname: "reason", label: __("Reason"), fieldtype: "Data", reqd: 1 }], __("Save"), (v) => run(frm, "hold", v)), null);
			btn(frm, __("Refused"), () => run(frm, "refuse"), null);
		},
	});

	// ---------------------------------------------------------------- laboratory
	frappe.ui.form.on("Lab Order", {
		refresh(frm) {
			if (frm.is_new()) return;
			if (frm.doc.has_critical) frm.dashboard.add_comment(__("This order has a critical result."), "red", true);
			const waiting = (frm.doc.tests || []).filter((t) => t.status === "Ordered");
			if (waiting.length) {
				btn(frm, __("Collect Samples"), () => collect(frm, waiting), null);
			}
			if (frm.doc.status !== "Completed" && frm.doc.status !== "Cancelled") {
				btn(frm, __("Cancel Order"), () => frappe.confirm(__("Cancel this order?"), () => run(frm, "cancel_order")), null);
			}
		},
	});
	async function collect(frm, rows) {
		for (const t of rows) await frm.call({ doc: frm.doc, method: "collect_sample", args: { row: t.name } });
		frappe.show_alert({ message: __("Samples collected. Result sheets are open for the lab."), indicator: "green" });
		frm.reload_doc();
	}
	frappe.ui.form.on("Lab Result", {
		refresh(frm) {
			if (frm.is_new()) return;
			if (frm.doc.has_critical) frm.dashboard.add_comment(__("Critical value: tell the doctor."), "red", true);
			if (frm.doc.status === "Draft") btn(frm, __("Mark Resulted"), () => frm.save().then(() => run(frm, "mark_resulted")), null);
			if (frm.doc.status === "Resulted") btn(frm, __("Verify"), () => run(frm, "verify"), null);
		},
	});

	// ---------------------------------------------------------------- radiology
	frappe.ui.form.on("Radiology Order", {
		refresh(frm) {
			if (frm.is_new()) return;
			const s = frm.doc.status;
			if (s === "Ordered") btn(frm, __("Schedule"), () => prompt(__("Schedule"), [{ fieldname: "at", label: __("Date and Time"), fieldtype: "Datetime", reqd: 1 }], __("Schedule"), (v) => run(frm, "schedule", v)), null);
			if (s === "Ordered" || s === "Scheduled") btn(frm, __("Mark Performed"), () => run(frm, "perform"), null);
			if (s === "Performed") btn(frm, __("Write Report"), () => prompt(__("Report"), [{ fieldname: "findings", label: __("Findings"), fieldtype: "Text", reqd: 1 }, { fieldname: "impression", label: __("Impression"), fieldtype: "Text", reqd: 1 },
				{ fieldname: "critical", label: __("Critical finding"), fieldtype: "Check" }], __("Save Report"), (v) => run(frm, "report", v)), null);
			if (s === "Reported") btn(frm, __("Verify"), () => run(frm, "verify"), null);
			if (s === "Ordered" || s === "Scheduled") btn(frm, __("Cancel Order"), () => frappe.confirm(__("Cancel this order?"), () => run(frm, "cancel_order")), null);
		},
	});

	// ---------------------------------------------------------------- surgery
	frappe.ui.form.on("Surgery Booking", {
		refresh(frm) {
			if (frm.is_new()) return;
			const s = frm.doc.status;
			if (s === "Booked") btn(frm, __("Mark Pre-op Ready"), () => run(frm, "mark_ready"), null);
			if (s === "Booked" || s === "Pre-op Ready") {
				btn(frm, __("Start Surgery"), () => run(frm, "start", { emergency: 0 }), null);
				btn(frm, __("Start as Emergency"), () => frappe.confirm(__("Start without the pre-op checklist complete?"), () => run(frm, "start", { emergency: 1 })), null);
				btn(frm, __("Cancel Booking"), () => prompt(__("Cancel Booking"), [{ fieldname: "reason", label: __("Reason"), fieldtype: "Data", reqd: 1 }], __("Cancel Booking"), (v) => run(frm, "cancel_booking", v)), null);
			}
			if (s === "In Progress") btn(frm, __("Complete Surgery"), () => prompt(__("Complete Surgery"), [{ fieldname: "operation_notes", label: __("Operation Notes"), fieldtype: "Text", reqd: 1, default: frm.doc.operation_notes },
				{ fieldname: "complications", label: __("Complications"), fieldtype: "Small Text", default: frm.doc.complications }], __("Complete"), (v) => run(frm, "complete", v)), null);
		},
	});

	// ---------------------------------------------------------------- emergency
	frappe.ui.form.on("Emergency Visit", {
		refresh(frm) {
			if (frm.is_new() || ["Admitted", "Discharged", "Transferred", "Deceased", "Left Without Being Seen"].includes(frm.doc.status)) return;
			btn(frm, __("Set Triage Level"), () => prompt(__("Triage"), [{ fieldname: "level", label: __("Level (1 = most urgent)"), fieldtype: "Select", options: "1\n2\n3\n4\n5", reqd: 1, default: frm.doc.triage_level }], __("Save"), (v) => run(frm, "set_triage", v)));
			btn(frm, __("Assign Doctor"), () => prompt(__("Assign Doctor"), [{ fieldname: "doctor", label: __("Doctor"), fieldtype: "Link", options: "Hospital Doctor", reqd: 1 }], __("Assign"), (v) => run(frm, "assign_doctor", v)));
			if (!frm.doc.patient) btn(frm, __("Link Patient"), () => prompt(__("Link Patient"), [{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Hospital Patient", reqd: 1 }], __("Link"), (v) => run(frm, "link_patient", v)));
			btn(frm, __("Admit to a Bed"), () => prompt(__("Admit"), [{ fieldname: "bed", label: __("Bed"), fieldtype: "Link", options: "Hospital Bed", reqd: 1,
				get_query: () => ({ filters: { branch: frm.doc.branch, status: "Available", active: 1 } }) }], __("Admit"), (v) => frm.call({ doc: frm.doc, method: "admit", args: v }).then((r) => r.message && frappe.set_route("Form", "Inpatient Admission", r.message))));
			btn(frm, __("Close Visit"), () => prompt(__("Close Visit"), [{ fieldname: "status", label: __("Outcome"), fieldtype: "Select", options: "Observation\nDischarged\nTransferred\nDeceased\nLeft Without Being Seen", reqd: 1 },
				{ fieldname: "note", label: __("Note"), fieldtype: "Small Text" }], __("Save"), (v) => run(frm, "dispose", v)));
		},
	});

	// ---------------------------------------------------------------- billing
	frappe.ui.form.on("Hospital Bill", {
		refresh(frm) {
			if (frm.doc.docstatus === 0) {
				btn(frm, __("Get Unbilled Charges"), () => frm.call({ doc: frm.doc, method: "load_charges", freeze: true }).then(() => frm.refresh()), null);
			}
			if (frm.doc.docstatus === 1 && frm.doc.patient_invoice && ["Unpaid", "Partly Paid"].includes(frm.doc.status)) {
				btn(frm, __("Receive Payment"), () => prompt(__("Receive Payment"), [{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: frm.doc.patient_outstanding },
					{ fieldname: "mode_of_payment", label: __("Mode of Payment"), fieldtype: "Link", options: "Mode of Payment", reqd: 1 }, { fieldname: "reference_no", label: __("Reference"), fieldtype: "Data" }], __("Receive"), (v) => run(frm, "receive_payment", v)), null);
			}
		},
	});
	frappe.ui.form.on("Insurance Claim", {
		refresh(frm) {
			if (frm.is_new()) return;
			if (frm.doc.status === "Draft") {
				btn(frm, __("Load Bills"), () => frm.call({ doc: frm.doc, method: "load_bills", freeze: true }).then(() => frm.refresh()), null);
				btn(frm, __("Send Claim"), () => frappe.confirm(__("Send the claim to the insurer? The bills are locked into it."), () => run(frm, "submit_claim")), null);
			} else {
				if (frm.doc.status !== "Paid" && frm.doc.status !== "Rejected") {
					btn(frm, __("Register Payment"), () => prompt(__("Insurer Payment"), [{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: frm.doc.outstanding },
						{ fieldname: "mode_of_payment", label: __("Mode of Payment"), fieldtype: "Link", options: "Mode of Payment", reqd: 1 }, { fieldname: "reference_no", label: __("Reference"), fieldtype: "Data" }], __("Register"), (v) => run(frm, "register_payment", v)), null);
					btn(frm, __("Record Rejection"), () => prompt(__("Rejection"), [{ fieldname: "row", label: __("Bill"), fieldtype: "Select", options: (frm.doc.lines || []).map((l) => ({ value: l.name, label: l.bill })), reqd: 1 },
						{ fieldname: "amount", label: __("Rejected Amount"), fieldtype: "Currency", reqd: 1 }, { fieldname: "reason", label: __("Reason"), fieldtype: "Data", reqd: 1 }], __("Save"), (v) => run(frm, "reject_line", v)), null);
				}
			}
		},
	});
	frappe.ui.form.on("Doctor Statement", {
		refresh(frm) {
			if (frm.is_new()) return;
			if (frm.doc.status === "Draft") {
				btn(frm, __("Load Fees"), () => frm.call({ doc: frm.doc, method: "load_rows", freeze: true }).then(() => frm.refresh()), null);
				btn(frm, __("Approve"), () => frappe.confirm(__("Approve the statement? Its fees can no longer go on another statement."), () => run(frm, "approve")), null);
			}
			if (frm.doc.status === "Approved") {
				if (!frm.doc.purchase_invoice) btn(frm, __("Create Payable"), () => run(frm, "create_payable"), null);
				else btn(frm, __("Refresh Payment Status"), () => run(frm, "refresh_status"), null);
			}
			if (["Draft", "Approved"].includes(frm.doc.status) && frm.doc.status !== "Draft") btn(frm, __("Cancel Statement"), () => frappe.confirm(__("Cancel the statement and release its fees?"), () => run(frm, "cancel_statement")), null);
		},
	});
})();
