"""Bed-day charging. A bed-day is counted each time the stay crosses the cutoff hour (default noon): a stay that never crosses it is still one day.
Admitted Mon 10:00, discharged Tue 11:00 -> crossed Mon 12:00 once -> 1 day. Discharged Tue 12:01 -> crossed twice -> 2 days.
Leaving exactly at the cutoff does not cross it. The posted count never goes down, and each charged day takes the rate of the bed the patient held at that cutoff."""
from datetime import datetime, time, timedelta


def first_cutoff(admit, cutoff_hour):
	c = datetime.combine(admit.date(), time(int(cutoff_hour), 0))
	return c if admit < c else c + timedelta(days=1)


def crossings(admit, until, cutoff_hour=12):
	"""Cutoff instants strictly after `admit` and strictly before `until`."""
	if until is None or until <= admit:
		return []
	out, c = [], first_cutoff(admit, cutoff_hour)
	while c < until:
		out.append(c)
		c += timedelta(days=1)
	return out


def bed_days(admit, until, cutoff_hour=12, min_days=1):
	return max(len(crossings(admit, until, cutoff_hour)), int(min_days))


def bed_at(segments, moment):
	"""The segment a patient was in at `moment`; before the first segment, the first; after the last open one, the last."""
	segs = sorted(segments, key=lambda s: s["from"])
	if not segs:
		return None
	chosen = segs[0]
	for s in segs:
		if s["from"] <= moment and (s.get("to") is None or moment < s["to"]):
			return s
		if s["from"] <= moment:
			chosen = s
	return chosen


def charge_days(segments, admit, until, cutoff_hour=12, min_days=1):
	"""Every charged day of the stay so far: [{n, date, bed, rate}]. `n` starts at 1 and the list only ever grows as `until` moves forward."""
	cuts = crossings(admit, until, cutoff_hour)
	total = max(len(cuts), int(min_days))
	out = []
	for i in range(total):
		moment = cuts[i] if i < len(cuts) else admit
		seg = bed_at(segments, moment)
		out.append({"n": i + 1, "date": moment.date(), "bed": seg["bed"] if seg else None, "rate": seg["rate"] if seg else 0})
	return out


def new_days(segments, admit, until, already_charged, cutoff_hour=12, min_days=1):
	"""Days still to post: the charged days after the first `already_charged`."""
	return charge_days(segments, admit, until, cutoff_hour, min_days)[int(already_charged):]


def occupancy_pct(occupied, total):
	return round(100.0 * occupied / total, 1) if total else 0.0
