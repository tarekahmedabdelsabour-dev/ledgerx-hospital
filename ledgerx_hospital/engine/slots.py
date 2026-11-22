"""Appointment slots from a doctor's schedule. Pure functions over plain values."""
from datetime import date, datetime, time, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def to_minutes(v):
	"""Minutes after midnight from time, timedelta, 'HH:MM[:SS]' or a number of minutes."""
	if v is None or v == "":
		return None
	if isinstance(v, time):
		return v.hour * 60 + v.minute
	if isinstance(v, timedelta):
		return int(v.total_seconds() // 60)
	if isinstance(v, (int, float)):
		return int(v)
	parts = str(v).split(":")
	return int(parts[0]) * 60 + int(parts[1])


def hhmm(m):
	return "%02d:%02d" % divmod(int(m), 60)


def weekday_name(d):
	return WEEKDAYS[d.weekday()]


def on_leave(d, time_offs):
	for t in time_offs or []:
		a, b = t.get("from_date"), t.get("to_date") or t.get("from_date")
		if a and a <= d <= b:
			return True
	return False


def day_slots(d, schedule, time_offs=(), booked=(), branch=None, now=None):
	"""Slots of one day: [{from, to, start, end, taken, capacity, free}].

	schedule rows: {weekday, from_time, to_time, slot_minutes, branch, capacity}; booked: [{start, end}] in any time form
	(cancelled or no-show appointments must not be passed). A slot is free when fewer than `capacity` booked appointments overlap it
	and, for today, it has not started yet.
	"""
	if on_leave(d, time_offs):
		return []
	now_min = None
	if now is not None and now.date() == d:
		now_min = now.hour * 60 + now.minute
	bk = [(to_minutes(b["start"]), to_minutes(b["end"])) for b in booked or []]
	out = []
	for row in schedule or []:
		if row.get("weekday") != weekday_name(d):
			continue
		if branch and row.get("branch") and row["branch"] != branch:
			continue
		step = int(row.get("slot_minutes") or 0)
		start, end = to_minutes(row.get("from_time")), to_minutes(row.get("to_time"))
		if step <= 0 or start is None or end is None:
			continue
		cap = max(int(row.get("capacity") or 1), 1)
		t = start
		while t + step <= end:
			taken = sum(1 for (a, b) in bk if a < t + step and b > t)
			past = now_min is not None and t <= now_min
			out.append({"from": hhmm(t), "to": hhmm(t + step), "start": t, "end": t + step, "taken": taken, "capacity": cap, "free": taken < cap and not past,
				"branch": row.get("branch")})
			t += step
	out.sort(key=lambda s: (s["start"], s.get("branch") or ""))
	return out


def slot_is_free(d, start, end, schedule, time_offs, booked, branch=None, now=None):
	"""True when [start, end) is exactly one of the doctor's free slots that day."""
	for s in day_slots(d, schedule, time_offs, booked, branch, now):
		if s["start"] == to_minutes(start) and s["end"] == to_minutes(end):
			return s["free"]
	return False


def is_follow_up(last_visit, visit, window_days):
	"""A follow-up when the previous paid consultation with the same doctor is at most `window_days` before this one."""
	if not last_visit or not window_days:
		return False
	gap = (visit - last_visit).days
	return 0 <= gap <= int(window_days)


def next_queue_no(numbers):
	nums = [int(n) for n in numbers or [] if n not in (None, "")]
	return (max(nums) if nums else 0) + 1
