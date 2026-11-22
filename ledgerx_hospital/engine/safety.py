"""Prescription safety hints. They only warn: the clinician decides. Matching is by whole words after Arabic and English normalisation,
so 'penicillin' warns for 'Penicillin V' but 'pen' does not warn for 'Penicillin'."""
import re

AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
TASHKEEL = re.compile("[ً-ٰٟـ]")
WORD = re.compile(r"[^\W_]+", re.U)
STOP = {"and", "or", "mg", "ml", "tablet", "tab", "capsule", "cap", "syrup", "injection", "cream", "w", "ال", "و"}


def words(text):
	t = TASHKEEL.sub("", str(text or "")).translate(AR_MAP).lower()
	return [w for w in WORD.findall(t) if len(w) > 2 and w not in STOP and not w.isdigit()]


def allergy_hits(allergies, drugs):
	"""allergies: text (comma / line separated) or a list; drugs: [{item, name, ingredient}] -> [{item, allergy}] where a whole allergy term appears in the drug's name or ingredient."""
	items = allergies if isinstance(allergies, (list, tuple)) else re.split(r"[,\n;،]+", str(allergies or ""))
	terms = [w for w in (words(x) for x in items) if w]
	hits = []
	for d in drugs or []:
		dw = set(words(d.get("name"))) | set(words(d.get("ingredient")))
		for t in terms:
			if all(w in dw for w in t):
				hits.append({"item": d.get("item"), "allergy": " ".join(t)})
	return hits


def duplicates(drugs):
	"""Two lines for the same item, or the same active ingredient: [(a, b)] by item code."""
	seen_item, seen_ing, out = {}, {}, []
	for d in drugs or []:
		code, ing = d.get("item"), (d.get("ingredient") or "").strip().lower()
		if code in seen_item:
			out.append((seen_item[code], code))
		else:
			seen_item[code] = code
		if ing:
			if ing in seen_ing and seen_ing[ing] != code:
				out.append((seen_ing[ing], code))
			seen_ing.setdefault(ing, code)
	return out
