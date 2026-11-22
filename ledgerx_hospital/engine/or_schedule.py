"""Operating-theatre booking conflicts: a room, surgeon or anaesthetist cannot be in two places at once. Pure functions."""
from datetime import timedelta


def overlaps(a_start, a_end, b_start, b_end):
	return a_start < b_end and b_start < a_end


def conflicts(new, existing, room_buffer_minutes=0):
	"""new / existing items: {name, start, end (datetime), room, people: [ids]}. Returns [(existing name, 'room' | person id)].
	The room needs `room_buffer_minutes` of cleaning after each case; people need none."""
	out = []
	buf = timedelta(minutes=int(room_buffer_minutes or 0))
	for e in existing:
		if new.get("name") and e.get("name") == new.get("name"):
			continue
		if new.get("room") and e.get("room") == new["room"] and overlaps(new["start"], new["end"] + buf, e["start"], e["end"] + buf):
			out.append((e.get("name"), "room"))
		for p in set(new.get("people") or []) & set(e.get("people") or []):
			if p and overlaps(new["start"], new["end"], e["start"], e["end"]):
				out.append((e.get("name"), p))
	return out


def case_end(start, minutes):
	return start + timedelta(minutes=int(minutes or 0))


def utilisation_pct(cases, day_start, day_end):
	"""Share of the day's minutes the room is booked: cases are [{start, end}] and are clipped to the day."""
	total = (day_end - day_start).total_seconds()
	if total <= 0:
		return 0.0
	used = 0.0
	spans = sorted((max(c["start"], day_start), min(c["end"], day_end)) for c in cases if c["end"] > day_start and c["start"] < day_end)
	cur_s = cur_e = None
	for s, e in spans:
		if cur_e is None or s > cur_e:
			if cur_e is not None:
				used += (cur_e - cur_s).total_seconds()
			cur_s, cur_e = s, e
		else:
			cur_e = max(cur_e, e)
	if cur_e is not None:
		used += (cur_e - cur_s).total_seconds()
	return round(100.0 * used / total, 1)
