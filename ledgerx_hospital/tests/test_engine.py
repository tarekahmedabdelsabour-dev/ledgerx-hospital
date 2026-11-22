import random
import unittest
from datetime import date, datetime, time, timedelta

from ledgerx_hospital.engine import beds, billing, claims, commission, lab, money, or_schedule, people, safety, slots, triage, vitals
from ledgerx_hospital.engine import stock

T = date(2026, 11, 20)


class Money(unittest.TestCase):
	def test_cents_half_up(self):
		self.assertEqual(money.cents(0.125), 13)
		self.assertEqual(money.cents(2.675), 268)  # float noise must not round down
		self.assertEqual(money.cents(-0.125), -13)
		self.assertEqual(money.cents(None), 0)
		self.assertEqual(money.pct_of(1000, 80), 800)
		self.assertEqual(money.pct_of(333, 50), 167)


class Billing(unittest.TestCase):
	PLAN = {"cover_pct": 80, "rules": [
		{"service_type": "Lab", "cover_pct": 100},
		{"service": "MRI", "cover_pct": 50, "requires_approval": 1},
		{"service_type": "Cosmetic", "excluded": 1},
		{"service": "CBC", "cover_pct": 100, "copay_fixed": 10},
		{"service": "Ward", "cover_pct": 100, "line_cap": 300},
	]}

	def L(self, amount, service="X", typ="Other", approved=False):
		return {"amount": amount, "service": service, "service_type": typ, "approved": approved}

	def test_cash_patient_pays_all(self):
		r = billing.split_bill([self.L(100), self.L(50)])
		self.assertEqual((r["insurer"], r["patient"], r["gross"]), (0, 150, 150))

	def test_default_and_type_rules(self):
		r = billing.split_bill([self.L(100), self.L(200, "ANY", "Lab")], self.PLAN)
		self.assertEqual([x["insurer"] for x in r["lines"]], [80, 200])
		self.assertEqual(r["patient"], 20)

	def test_service_beats_type(self):
		r = billing.split_bill([self.L(100, "CBC", "Lab")], self.PLAN)
		self.assertEqual(r["lines"][0]["insurer"], 90)  # 100% but the patient keeps the fixed 10

	def test_exclusion_and_approval(self):
		r = billing.split_bill([self.L(500, "X", "Cosmetic"), self.L(1000, "MRI", "Radiology")], self.PLAN)
		self.assertEqual([x["insurer"] for x in r["lines"]], [0, 0])
		self.assertEqual(r["lines"][0]["reason"], "Excluded")
		self.assertEqual(r["lines"][1]["reason"], "Needs approval")
		r = billing.split_bill([self.L(1000, "MRI", "Radiology", approved=True)], self.PLAN)
		self.assertEqual(r["insurer"], 500)

	def test_line_cap(self):
		r = billing.split_bill([self.L(1000, "Ward")], self.PLAN)
		self.assertEqual(r["insurer"], 300)

	def test_patient_cap_moves_excess_to_insurer(self):
		plan = {"cover_pct": 50, "patient_cap": 100}
		r = billing.split_bill([self.L(400), self.L(400)], plan)
		self.assertEqual(r["patient"], 100)
		self.assertEqual(r["insurer"], 700)
		# uncovered (excluded) lines are not capped
		plan = {"cover_pct": 50, "patient_cap": 100, "rules": [{"service": "Z", "excluded": 1}]}
		r = billing.split_bill([self.L(400), self.L(300, "Z")], plan)
		self.assertEqual(r["patient"], 100 + 300)

	def test_visit_copay_floor(self):
		plan = {"cover_pct": 100, "visit_copay": 50}
		r = billing.split_bill([self.L(30), self.L(120)], plan)
		self.assertEqual(r["patient"], 50)
		self.assertEqual(r["insurer"], 100)
		r = billing.split_bill([self.L(30)], plan)  # the patient never pays more than the bill
		self.assertEqual((r["patient"], r["insurer"]), (30, 0))

	def test_annual_limit(self):
		r = billing.split_bill([self.L(100), self.L(100)], {"cover_pct": 100}, annual_remaining=150)
		self.assertEqual(r["insurer"], 150)
		self.assertEqual(r["patient"], 50)
		r = billing.split_bill([self.L(100)], {"cover_pct": 100}, annual_remaining=0)
		self.assertEqual(r["insurer"], 0)

	def test_credit_lines(self):
		r = billing.split_bill([self.L(100), self.L(-40)], {"cover_pct": 50})
		self.assertEqual([x["insurer"] for x in r["lines"]], [50, -20])

	def test_conservation_random(self):
		rnd = random.Random(11)
		for _ in range(2000):
			lines = [self.L(round(rnd.choice([0, 0.01, 9.99, 33.33, 100, 250.5, 1200]) * rnd.choice([1, 1, 1, -1]), 2), rnd.choice(["CBC", "MRI", "Ward", "X"]),
				rnd.choice(["Lab", "Cosmetic", "Radiology", "Other"]), rnd.random() < .5) for _ in range(rnd.randint(0, 7))]
			plan = None if rnd.random() < .15 else {"cover_pct": rnd.choice([0, 30, 70, 100]), "rules": self.PLAN["rules"],
				"patient_cap": rnd.choice([None, 0, 50, 500]), "visit_copay": rnd.choice([0, 20, 5000])}
			rem = rnd.choice([None, 0, 100, 10000])
			r = billing.split_bill(lines, plan, rem)
			ci, cp = sum(money.cents(x["insurer"]) for x in r["lines"]), sum(money.cents(x["patient"]) for x in r["lines"])
			self.assertEqual(ci + cp, sum(money.cents(l["amount"]) for l in lines))
			self.assertEqual(ci, money.cents(r["insurer"]))
			if rem is not None:
				self.assertLessEqual(ci, max(money.cents(rem), 0) + sum(1 for l in lines if l["amount"] < 0) * 0 + abs(sum(min(money.cents(x["insurer"]), 0) for x in r["lines"])))
			for l, x in zip(lines, r["lines"]):
				if l["amount"] > 0:
					self.assertGreaterEqual(x["insurer"], 0)
					self.assertLessEqual(x["insurer"], l["amount"])

	def test_line_net(self):
		self.assertEqual(billing.line_net(99.99, 3, 10), 269.97)
		self.assertEqual(billing.line_net(10, 2, 0), 20.0)


class Commission(unittest.TestCase):
	RULES = [{"mode": "Percent", "value": 40}, {"service_type": "Surgery", "mode": "Percent", "value": 60},
		{"service": "CONS", "mode": "Fixed", "value": 100}, {"service": "CONS", "payer": "Insurance", "mode": "Percent", "value": 30}]

	def test_specificity(self):
		r = commission.pick_rule(self.RULES, "CONS", "Consultation", "Cash")
		self.assertEqual((r["mode"], r["value"]), ("Fixed", 100))
		r = commission.pick_rule(self.RULES, "CONS", "Consultation", "Insurance")
		self.assertEqual((r["mode"], r["value"]), ("Percent", 30))
		r = commission.pick_rule(self.RULES, "OP1", "Surgery", "Cash")
		self.assertEqual(r["value"], 60)
		r = commission.pick_rule(self.RULES, "ZZ", "Lab", "Cash")
		self.assertEqual(r["value"], 40)
		self.assertIsNone(commission.pick_rule([{"service": "A", "value": 1}], "B", "x", "Cash"))

	def test_amounts(self):
		self.assertEqual(commission.doctor_share(1000, 1, {"mode": "Percent", "value": 35}), 350)
		self.assertEqual(commission.doctor_share(300, 2, {"mode": "Fixed", "value": 100}), 200)
		self.assertEqual(commission.doctor_share(150, 3, {"mode": "Fixed", "value": 100}), 150)  # never more than the amount
		self.assertEqual(commission.doctor_share(-200, 1, {"mode": "Percent", "value": 50}), -100)
		self.assertEqual(commission.doctor_share(100, 1, None), 0)

	def test_statement(self):
		g, s, n = commission.statement_totals([{"amount": 100, "share": 40}, {"amount": 50, "share": 20}], deductions=15)
		self.assertEqual((g, s, n), (150, 60, 45))
		self.assertEqual(commission.statement_totals([{"amount": 10, "share": 5}], 99)[2], 0)


class Slots(unittest.TestCase):
	SCH = [{"weekday": "Friday", "from_time": time(9), "to_time": time(11), "slot_minutes": 30, "branch": "B1", "capacity": 1}]

	def test_weekday_and_count(self):
		d = date(2026, 11, 20)  # a Friday
		self.assertEqual(slots.weekday_name(d), "Friday")
		s = slots.day_slots(d, self.SCH)
		self.assertEqual([x["from"] for x in s], ["09:00", "09:30", "10:00", "10:30"])
		self.assertEqual(slots.day_slots(date(2026, 11, 21), self.SCH), [])

	def test_booked_leave_and_past(self):
		d = date(2026, 11, 20)
		s = slots.day_slots(d, self.SCH, booked=[{"start": time(9, 30), "end": time(10)}])
		self.assertEqual([x["free"] for x in s], [True, False, True, True])
		self.assertEqual(slots.day_slots(d, self.SCH, time_offs=[{"from_date": date(2026, 11, 19), "to_date": date(2026, 11, 21)}]), [])
		s = slots.day_slots(d, self.SCH, now=datetime(2026, 11, 20, 9, 45))
		self.assertEqual([x["free"] for x in s], [False, False, True, True])

	def test_capacity_and_timedelta_inputs(self):
		sch = [{"weekday": "Friday", "from_time": timedelta(hours=9), "to_time": "10:00:00", "slot_minutes": 30, "capacity": 2}]
		d = date(2026, 11, 20)
		b = [{"start": "09:00", "end": "09:30"}]
		self.assertTrue(slots.day_slots(d, sch, booked=b)[0]["free"])
		self.assertFalse(slots.day_slots(d, sch, booked=b * 2)[0]["free"])
		self.assertTrue(slots.slot_is_free(d, "09:30", "10:00", sch, [], b))
		self.assertFalse(slots.slot_is_free(d, "09:15", "09:45", sch, [], b))  # not one of the slots

	def test_branch_filter_followup_queue(self):
		d = date(2026, 11, 20)
		self.assertEqual(slots.day_slots(d, self.SCH, branch="B2"), [])
		self.assertTrue(slots.is_follow_up(date(2026, 11, 10), d, 14))
		self.assertFalse(slots.is_follow_up(date(2026, 10, 1), d, 14))
		self.assertFalse(slots.is_follow_up(None, d, 14))
		self.assertFalse(slots.is_follow_up(date(2026, 11, 25), d, 14))
		self.assertEqual(slots.next_queue_no([1, 5, 3]), 6)
		self.assertEqual(slots.next_queue_no([]), 1)


class Beds(unittest.TestCase):
	def D(self, d, h, m=0):
		return datetime(2026, 11, d, h, m)

	def test_day_counts(self):
		a = self.D(2, 10)
		self.assertEqual(beds.bed_days(a, self.D(2, 11)), 1)  # never crossed noon: still one
		self.assertEqual(beds.bed_days(a, self.D(3, 11)), 1)
		self.assertEqual(beds.bed_days(a, self.D(3, 12)), 1)  # leaving exactly at the cutoff
		self.assertEqual(beds.bed_days(a, self.D(3, 12, 1)), 2)
		self.assertEqual(beds.bed_days(self.D(2, 14), self.D(3, 11)), 1)
		self.assertEqual(beds.bed_days(self.D(2, 14), self.D(4, 13)), 2)
		self.assertEqual(beds.bed_days(a, self.D(9, 9)), 7)  # noons of the 2nd..8th
		self.assertEqual(beds.bed_days(a, None), 1)

	def test_never_decreases(self):
		a = self.D(2, 10)
		prev = 0
		for h in range(0, 24 * 9):
			n = beds.bed_days(a, a + timedelta(hours=h))
			self.assertGreaterEqual(n, prev)
			prev = n

	def test_transfer_takes_rate_at_cutoff(self):
		a = self.D(2, 10)
		segs = [{"bed": "W1", "rate": 500, "from": a, "to": self.D(3, 15)}, {"bed": "ICU", "rate": 2000, "from": self.D(3, 15), "to": None}]
		days = beds.charge_days(segs, a, self.D(5, 13))
		self.assertEqual([(d["n"], d["bed"], d["rate"]) for d in days], [(1, "W1", 500), (2, "W1", 500), (3, "ICU", 2000), (4, "ICU", 2000)])
		self.assertEqual([d["date"] for d in days], [date(2026, 11, d) for d in (2, 3, 4, 5)])

	def test_new_days_idempotent(self):
		a = self.D(2, 10)
		segs = [{"bed": "W1", "rate": 500, "from": a, "to": None}]
		now = self.D(4, 13)
		total = len(beds.charge_days(segs, a, now))
		self.assertEqual(len(beds.new_days(segs, a, now, 0)), total)
		self.assertEqual(beds.new_days(segs, a, now, total), [])
		self.assertEqual(len(beds.new_days(segs, a, now, 1)), total - 1)

	def test_occupancy(self):
		self.assertEqual(beds.occupancy_pct(3, 8), 37.5)
		self.assertEqual(beds.occupancy_pct(0, 0), 0.0)


class Lab(unittest.TestCase):
	def test_parse(self):
		self.assertEqual(lab.parse_number("5.2"), (5.2, ""))
		self.assertEqual(lab.parse_number("٥٫٢"), (5.2, ""))
		self.assertEqual(lab.parse_number("5,2"), (5.2, ""))
		self.assertEqual(lab.parse_number("1,200"), (None, None))  # ambiguous: left to a person
		self.assertEqual(lab.parse_number("5,25"), (5.25, ""))
		self.assertEqual(lab.parse_number("<0.5"), (0.5, "<"))
		self.assertEqual(lab.parse_number("positive"), (None, None))
		self.assertEqual(lab.parse_number(""), (None, None))

	def test_ranges(self):
		rs = [{"gender": "Any", "low": 12, "high": 16}, {"gender": "Female", "low": 11.5, "high": 15}, {"gender": "Male", "age_from": 0, "age_to": 1, "low": 14, "high": 22}]
		self.assertEqual(lab.pick_range(rs, "Female", 30)["low"], 11.5)
		self.assertEqual(lab.pick_range(rs, "Male", 30)["low"], 12)
		self.assertEqual(lab.pick_range(rs, "Male", 0.5)["low"], 14)
		self.assertEqual(lab.pick_range(rs, "Male", None)["low"], 12)  # age unknown: the bounded range is not used
		self.assertIsNone(lab.pick_range([], "Male", 3))

	def test_flags_and_boundaries(self):
		r = {"low": 10, "high": 20, "crit_low": 5, "crit_high": 30}
		self.assertEqual([lab.flag(v, r) for v in (4, 5, 9.9, 10, 20, 20.1, 30, 31)], ["Critical Low", "Low", "Low", "Normal", "Normal", "High", "High", "Critical High"])
		self.assertEqual(lab.flag(None, r), "")
		self.assertEqual(lab.flag(5, None), "")
		self.assertTrue(lab.is_critical("Critical Low"))
		self.assertFalse(lab.is_critical("Low"))

	def test_operators_never_overclaim(self):
		r = {"low": 10, "high": 20}
		self.assertEqual(lab.flag_text("<5", r), "Low")
		self.assertEqual(lab.flag_text("<15", r), "")  # could be anywhere below 15
		self.assertEqual(lab.flag_text(">25", r), "High")
		self.assertEqual(lab.flag_text(">12", r), "")
		self.assertEqual(lab.flag_text("15", r), "Normal")
		self.assertEqual(lab.flag_text("reactive", r), "")


class OR(unittest.TestCase):
	def D(self, h, m=0):
		return datetime(2026, 11, 20, h, m)

	def test_room_people_and_buffer(self):
		ex = [{"name": "S1", "start": self.D(9), "end": self.D(11), "room": "OR1", "people": ["Dr A", "Dr X"]}]
		self.assertEqual(or_schedule.conflicts({"start": self.D(10), "end": self.D(12), "room": "OR1", "people": []}, ex), [("S1", "room")])
		self.assertEqual(or_schedule.conflicts({"start": self.D(11), "end": self.D(12), "room": "OR1", "people": []}, ex), [])
		self.assertEqual(or_schedule.conflicts({"start": self.D(11), "end": self.D(12), "room": "OR1", "people": []}, ex, 30), [("S1", "room")])
		self.assertEqual(or_schedule.conflicts({"start": self.D(11, 30), "end": self.D(12), "room": "OR1", "people": []}, ex, 30), [])
		c = or_schedule.conflicts({"start": self.D(10), "end": self.D(10, 30), "room": "OR2", "people": ["Dr A"]}, ex)
		self.assertEqual(c, [("S1", "Dr A")])
		self.assertEqual(or_schedule.conflicts({"name": "S1", "start": self.D(10), "end": self.D(12), "room": "OR1"}, ex), [])  # editing itself

	def test_utilisation(self):
		cases = [{"start": self.D(8), "end": self.D(10)}, {"start": self.D(9), "end": self.D(11)}, {"start": self.D(14), "end": self.D(16)}]
		self.assertEqual(or_schedule.utilisation_pct(cases, self.D(8), self.D(16)), 62.5)
		self.assertEqual(or_schedule.utilisation_pct([], self.D(8), self.D(16)), 0.0)


class Triage(unittest.TestCase):
	def test_order_and_overdue(self):
		n = datetime(2026, 11, 20, 12)
		v = [{"name": "a", "level": 3, "arrival": n - timedelta(minutes=50)}, {"name": "b", "level": 1, "arrival": n - timedelta(minutes=2)},
			{"name": "c", "level": 3, "arrival": n - timedelta(minutes=80)}, {"name": "d", "level": None, "arrival": n - timedelta(minutes=300)}]
		self.assertEqual([x["name"] for x in triage.queue_order(v)], ["b", "c", "a", "d"])
		self.assertTrue(triage.is_overdue(3, n - timedelta(minutes=50), n))
		self.assertFalse(triage.is_overdue(3, n - timedelta(minutes=30), n))
		self.assertFalse(triage.is_overdue(1, n - timedelta(minutes=99), n, seen_at=n))
		self.assertTrue(triage.is_overdue(1, n - timedelta(minutes=1), n))

	def test_door_to_doctor(self):
		n = datetime(2026, 11, 20, 12)
		r = triage.door_to_doctor([{"arrival": n, "seen_at": n + timedelta(minutes=10)}, {"arrival": n, "seen_at": n + timedelta(minutes=30)}, {"arrival": n}])
		self.assertEqual(r, {"seen": 2, "average": 20.0, "worst": 30})
		self.assertEqual(triage.door_to_doctor([])["seen"], 0)


class Safety(unittest.TestCase):
	def test_allergy_whole_words(self):
		drugs = [{"item": "I1", "name": "Penicillin V 500mg", "ingredient": "Phenoxymethylpenicillin"}, {"item": "I2", "name": "Panadol", "ingredient": "Paracetamol"}]
		self.assertEqual(safety.allergy_hits("Penicillin, latex", drugs), [{"item": "I1", "allergy": "penicillin"}])
		self.assertEqual(safety.allergy_hits("pen", drugs), [])
		self.assertEqual(safety.allergy_hits(["باراسيتامول"], [{"item": "I3", "name": "x", "ingredient": "باراسيتامول"}])[0]["item"], "I3")
		self.assertEqual(safety.allergy_hits("", drugs), [])

	def test_arabic_folding(self):
		self.assertEqual(safety.allergy_hits("أموكسيسيلين", [{"item": "A", "name": "اموكسيسيلين"}])[0]["item"], "A")

	def test_duplicates(self):
		d = [{"item": "A", "ingredient": "Ibuprofen"}, {"item": "B", "ingredient": "ibuprofen"}, {"item": "A", "ingredient": "Ibuprofen"}]
		self.assertEqual(safety.duplicates(d), [("A", "B"), ("A", "A")])
		self.assertEqual(safety.duplicates([{"item": "A"}, {"item": "B"}]), [])


class People(unittest.TestCase):
	def test_national_id(self):
		r = people.parse_national_id("29001010100011")
		self.assertTrue(r["valid"])
		self.assertEqual((r["birth_date"], r["gender"], r["governorate"]), (date(1990, 1, 1), "Male", "Cairo"))
		r = people.parse_national_id("٣٠٣٠٢٢٨٢١٠٠٠٢٢")
		self.assertTrue(r["valid"])
		self.assertEqual((r["birth_date"], r["gender"], r["governorate"]), (date(2003, 2, 28), "Female", "Giza"))
		for bad in ("2900101010001", "290010101000111", "49001010100011", "29002300100011", "29002300x00011", "", None, "35001010100011"):
			self.assertFalse(people.parse_national_id(bad)["valid"], bad)

	def test_age(self):
		self.assertEqual(people.age_parts(date(2000, 2, 29), date(2026, 2, 28)), (25, 11, 30))
		self.assertEqual(people.age_years(date(2000, 11, 21), date(2026, 11, 20)), 25)
		self.assertEqual(people.age_years(date(2000, 11, 20), date(2026, 11, 20)), 26)
		self.assertEqual(people.age_parts(date(2026, 12, 1), date(2026, 11, 20)), (0, 0, 0))
		self.assertEqual(people.age_text(date(2026, 11, 10), date(2026, 11, 20)), "10 d")
		self.assertEqual(people.age_text(date(2026, 5, 20), date(2026, 11, 20)), "6 mo")
		self.assertEqual(people.age_text(date(2020, 5, 20), date(2026, 11, 20), "ar"), "6 سنة")


class Vitals(unittest.TestCase):
	def test_bmi(self):
		self.assertEqual(vitals.bmi(70, 175), 22.9)
		self.assertIsNone(vitals.bmi(0, 175))
		self.assertIsNone(vitals.bmi("x", 175))
		self.assertEqual([vitals.bmi_band(v) for v in (17, 18.5, 24.9, 25, 29.9, 30)], ["Underweight", "Normal", "Normal", "Overweight", "Overweight", "Obese"])
		self.assertEqual(vitals.bmi_band(22, adult=False), "")

	def test_out_of_range(self):
		r = vitals.out_of_range({"sys_bp": 150, "dia_bp": 70, "pulse": 40, "spo2": 90, "temperature": 38.0, "resp_rate": ""})
		self.assertEqual(r, {"sys_bp": "High", "pulse": "Low", "spo2": "Low"})
		self.assertEqual(vitals.out_of_range({"pulse": 130}, {"pulse": (60, 120)}), {"pulse": "High"})


class Claims(unittest.TestCase):
	def test_status(self):
		self.assertEqual(claims.claim_status(1000, 0, 0, False), "Draft")
		self.assertEqual(claims.claim_status(1000, 0, 0, True), "Submitted")
		self.assertEqual(claims.claim_status(1000, 400, 0, True), "Partially Paid")
		self.assertEqual(claims.claim_status(1000, 900, 100, True), "Paid")
		self.assertEqual(claims.claim_status(1000, 0, 1000, True), "Rejected")
		self.assertEqual(claims.claim_status(1000, 0, 100, True), "Partially Paid")
		self.assertEqual(claims.outstanding(1000, 400, 100), 500)
		self.assertEqual(claims.outstanding(1000, 1200, 0), 0)

	def test_aging(self):
		self.assertEqual([claims.aging_bucket(d) for d in (-5, 0, 30, 31, 90, 91, 120, 121)], ["0-30", "0-30", "0-30", "31-60", "61-90", "91-120", "91-120", "120+"])

	def test_spread_oldest_first(self):
		lines = [{"name": "B", "due": date(2026, 2, 1), "open": 50}, {"name": "A", "due": date(2026, 1, 1), "open": 100}, {"name": "C", "due": date(2026, 3, 1), "open": 70}]
		self.assertEqual(claims.spread_payment(lines, 120), ([("A", 100), ("B", 20)], 0))
		self.assertEqual(claims.spread_payment(lines, 500), ([("A", 100), ("B", 50), ("C", 70)], 280))
		self.assertEqual(claims.spread_payment(lines, 0), ([], 0))


class Stock(unittest.TestCase):
	def test_fefo(self):
		b = [{"batch_no": "B", "qty": 5, "expiry": T + timedelta(days=200)}, {"batch_no": "A", "qty": 3, "expiry": T + timedelta(days=60)}, {"batch_no": "X", "qty": 9, "expiry": T - timedelta(days=1)}]
		alloc, short = stock.fefo_allocate(b, 7, T)
		self.assertEqual((alloc, short), ([("A", 3), ("B", 4)], 0))


if __name__ == "__main__":
	unittest.main()
