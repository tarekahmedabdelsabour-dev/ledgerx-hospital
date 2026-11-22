"""Emergency queue. ESI levels: 1 = resuscitation ... 5 = non-urgent. Target minutes to a doctor are defaults a hospital can change."""
TARGETS = {1: 0, 2: 10, 3: 30, 4: 60, 5: 120}
COLORS = {1: "Red", 2: "Orange", 3: "Yellow", 4: "Green", 5: "Blue"}


def wait_minutes(arrival, now, seen_at=None):
	end = seen_at or now
	return max(int((end - arrival).total_seconds() // 60), 0)


def is_overdue(level, arrival, now, seen_at=None, targets=None):
	if seen_at:
		return False
	return wait_minutes(arrival, now) > (targets or TARGETS).get(int(level), 120)


def queue_order(visits):
	"""Sickest first (level 1 before 5), then the longest waiting. Visits without a level go last. Returns a new list."""
	return sorted(visits, key=lambda v: (v.get("level") or 9, v["arrival"], str(v.get("name"))))


def door_to_doctor(visits):
	"""Average and worst minutes from arrival to being seen, over the visits that were seen."""
	ws = [wait_minutes(v["arrival"], v["seen_at"], v["seen_at"]) for v in visits if v.get("seen_at")]
	if not ws:
		return {"seen": 0, "average": 0.0, "worst": 0}
	return {"seen": len(ws), "average": round(sum(ws) / len(ws), 1), "worst": max(ws)}
