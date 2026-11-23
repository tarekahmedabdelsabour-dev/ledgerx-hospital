"""Every Link / Table field of every DocType points at a DocType of this app or a known standard one; every field_order entry exists."""
import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "ledgerx_hospital", "hospital", "doctype")
EXTERNAL = set("""Company|Price List|Item|Item Group|Customer|Supplier|Employee|User|Account|Cost Center|Warehouse|Mode of Payment|Payment Entry|Sales Invoice|Purchase Invoice|Stock Entry|Journal Entry|UOM|Sales Taxes and Charges Template|Role""".split("|"))
mine = {}
for f in glob.glob(os.path.join(ROOT, "*", "*.json")):
	d = json.load(open(f))
	mine[d["name"]] = d
bad = 0
for name, d in mine.items():
	names = [x["fieldname"] for x in d["fields"]]
	if len(names) != len(set(names)):
		print(name, "duplicate fieldnames"); bad += 1
	if names != d["field_order"]:
		print(name, "field_order mismatch"); bad += 1
	for x in d["fields"]:
		if x["fieldtype"] in ("Link", "Table", "Table MultiSelect") and x.get("options") not in mine and x.get("options") not in EXTERNAL:
			print(name, x["fieldname"], "->", x.get("options")); bad += 1
		if x["fieldtype"] == "Table" and not mine.get(x.get("options"), {}).get("istable"):
			print(name, x["fieldname"], "table points at a non-table"); bad += 1
		if x.get("fetch_from"):
			link = x["fetch_from"].split(".")[0]
			if link not in names:
				print(name, x["fieldname"], "fetch_from link missing", link); bad += 1
	if d.get("autoname", "").startswith("field:"):
		fn = d["autoname"][6:]
		if fn not in names:
			print(name, "autoname field missing"); bad += 1
	if d.get("title_field") and d["title_field"] not in names:
		print(name, "title_field missing"); bad += 1
print(len(mine), "doctypes,", bad, "problems")
sys.exit(1 if bad else 0)
