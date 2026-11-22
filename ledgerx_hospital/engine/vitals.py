"""Vital signs: BMI and a highlight of readings outside ranges the hospital sets. Highlighting is not a diagnosis or a risk score."""
DEFAULT_LIMITS = {"sys_bp": (90, 140), "dia_bp": (60, 90), "pulse": (50, 110), "resp_rate": (12, 24), "spo2": (92, 100), "temperature": (36.0, 38.0)}
BMI_BANDS = [(18.5, "Underweight"), (25, "Normal"), (30, "Overweight"), (None, "Obese")]


def bmi(weight_kg, height_cm):
	try:
		w, h = float(weight_kg), float(height_cm) / 100.0
	except (TypeError, ValueError):
		return None
	if w <= 0 or h <= 0:
		return None
	return round(w / (h * h), 1)


def bmi_band(value, adult=True):
	"""Adult WHO bands only; children are not banded (their BMI needs growth charts)."""
	if value is None or not adult:
		return ""
	for limit, name in BMI_BANDS:
		if limit is None or value < limit:
			return name
	return ""


def out_of_range(readings, limits=None):
	"""{field: 'Low'|'High'} for the readings outside their (low, high) limits; blank readings are skipped."""
	lim = dict(DEFAULT_LIMITS)
	lim.update(limits or {})
	out = {}
	for k, (lo, hi) in lim.items():
		v = readings.get(k)
		if v in (None, "", 0):
			continue
		v = float(v)
		if lo is not None and v < lo:
			out[k] = "Low"
		elif hi is not None and v > hi:
			out[k] = "High"
	return out
