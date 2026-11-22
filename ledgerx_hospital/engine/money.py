"""Money in whole cents, so shares always add up exactly."""
from decimal import ROUND_HALF_UP, Decimal


def cents(x):
	"""A number as integer cents, rounding half up (away from zero for negatives)."""
	if x in (None, ""):
		return 0
	d = Decimal(str(x)) * 100
	return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP)) if d >= 0 else -int((-d).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money(c):
	return round(c / 100.0, 2)


def pct_of(c, pct):
	"""`pct` percent of `c` cents, rounded half up to a whole cent."""
	d = Decimal(c) * Decimal(str(pct)) / 100
	return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP)) if d >= 0 else -int((-d).quantize(Decimal(1), rounding=ROUND_HALF_UP))
