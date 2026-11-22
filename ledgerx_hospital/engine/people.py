"""Patient identity: age and the Egyptian national ID (14 digits)."""
from datetime import date

AR = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
GOVERNORATES = {
	"01": "Cairo", "02": "Alexandria", "03": "Port Said", "04": "Suez", "11": "Damietta", "12": "Dakahlia", "13": "Sharqia", "14": "Qalyubia",
	"15": "Kafr El Sheikh", "16": "Gharbia", "17": "Monufia", "18": "Beheira", "19": "Ismailia", "21": "Giza", "22": "Beni Suef", "23": "Fayoum",
	"24": "Minya", "25": "Assiut", "26": "Sohag", "27": "Qena", "28": "Aswan", "29": "Luxor", "31": "Red Sea", "32": "New Valley", "33": "Matrouh",
	"34": "North Sinai", "35": "South Sinai", "88": "Born abroad",
}


def parse_national_id(value):
	"""{valid, birth_date, gender, governorate}. Valid means 14 digits, century digit 2 or 3 and a real birth date not in the future."""
	s = str(value or "").translate(AR).strip()
	bad = {"valid": False, "birth_date": None, "gender": None, "governorate": None}
	if len(s) != 14 or not s.isdigit() or s[0] not in "23":
		return bad
	year = (1900 if s[0] == "2" else 2000) + int(s[1:3])
	try:
		born = date(year, int(s[3:5]), int(s[5:7]))
	except ValueError:
		return bad
	if born > date.today():
		return bad
	return {"valid": True, "birth_date": born, "gender": "Male" if int(s[12]) % 2 else "Female", "governorate": GOVERNORATES.get(s[7:9])}


def age_parts(born, on=None):
	"""(years, months, days) between two dates."""
	on = on or date.today()
	if not born or born > on:
		return 0, 0, 0
	y, m, d = on.year - born.year, on.month - born.month, on.day - born.day
	if d < 0:
		m -= 1
		prev_month_days = (date(on.year, on.month, 1) - date.resolution).day
		d += prev_month_days
	if m < 0:
		y -= 1
		m += 12
	return y, m, d


def age_years(born, on=None):
	return age_parts(born, on)[0]


def age_text(born, on=None, lang="en"):
	y, m, d = age_parts(born, on)
	if y >= 2:
		return ("%d سنة" if lang == "ar" else "%d y") % y
	if y == 1 or m >= 1:
		total_m = y * 12 + m
		return ("%d شهر" if lang == "ar" else "%d mo") % total_m
	return ("%d يوم" if lang == "ar" else "%d d") % d
