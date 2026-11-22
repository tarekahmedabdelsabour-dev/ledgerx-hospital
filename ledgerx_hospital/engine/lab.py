"""Lab result handling: reading a typed value and flagging it against the right reference range."""
import re

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def parse_number(text):
	"""(value, operator) from '5.2', '٥٫٢', '5,2', '<0.5', '>1000'; (None, None) when it is not a number. Operator is '' or '<' / '>' / '<=' / '>='."""
	if text is None:
		return None, None
	s = str(text).translate(AR_DIGITS).strip().replace(" ", "")
	m = re.fullmatch(r"(<=|>=|<|>)?(-?\d+(?:[.,]\d+)?)", s)
	if not m:
		return None, None
	num = m.group(2)
	if "," in num:
		# '5,2' is a decimal comma; '1,200' could be 1.2 or 1200, so it is not read at all and a person decides
		if re.fullmatch(r"-?\d{1,3},\d{3}", num):
			return None, None
		num = num.replace(",", ".")
	return float(num), (m.group(1) or "")


def pick_range(ranges, gender=None, age_years=None):
	"""The most specific reference range for the patient. A range matches when its gender is Any (or equal) and the age is inside [age_from, age_to] (blank = open).
	An exact gender beats Any, then a bounded age beats an open one; ties go to the first row."""
	best, best_rank = None, -1
	for r in ranges or []:
		g = r.get("gender") or "Any"
		if g != "Any" and g != gender:
			continue
		lo, hi = r.get("age_from"), r.get("age_to")
		if age_years is not None:
			if lo not in (None, "") and age_years < float(lo):
				continue
			if hi not in (None, "") and age_years > float(hi):
				continue
		elif lo not in (None, "") or hi not in (None, ""):
			continue  # age unknown: only age-free ranges can be used
		rank = (2 if g != "Any" else 0) + (1 if lo not in (None, "") or hi not in (None, "") else 0)
		if rank > best_rank:
			best, best_rank = r, rank
	return best


def flag(value, rng):
	"""'Normal', 'Low', 'High', 'Critical Low', 'Critical High', or '' when there is no number or no range."""
	if value is None or not rng:
		return ""
	def num(k):
		v = rng.get(k)
		return None if v in (None, "") else float(v)
	lo, hi, clo, chi = num("low"), num("high"), num("crit_low"), num("crit_high")
	if clo is not None and value < clo:
		return "Critical Low"
	if chi is not None and value > chi:
		return "Critical High"
	if lo is not None and value < lo:
		return "Low"
	if hi is not None and value > hi:
		return "High"
	return "Normal" if (lo is not None or hi is not None) else ""


def flag_text(text, rng):
	"""Flag for a typed result. '<0.5' means the true value is below 0.5, so it can only be called Low (or Critical Low) when 0.5 itself is;
	'>100' likewise for High. In every other case it is left unflagged for a person to judge."""
	v, op = parse_number(text)
	if v is None:
		return ""
	f = flag(v, rng)
	if op in ("<", "<="):
		return f if f in ("Low", "Critical Low") else ""
	if op in (">", ">="):
		return f if f in ("High", "Critical High") else ""
	return f


def is_critical(f):
	return f.startswith("Critical")
