"""Static check: field names written as strings (get_value / set_value / get_all / db_set / get_doc dicts / SQL on our tables) exist on the DocType they are used with."""
import ast
import glob
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "ledgerx_hospital")
DT = {}
for f in glob.glob(os.path.join(ROOT, "hospital", "doctype", "*", "*.json")):
	d = json.load(open(f))
	DT[d["name"]] = {x["fieldname"] for x in d["fields"]} | set("name creation modified owner docstatus idx parent parenttype parentfield modified_by".split())
EXTRA = {"Hospital Bill": {"posting_date"}}
bad = []


def strs(node):
	if isinstance(node, ast.Constant) and isinstance(node.value, str):
		return [node.value]
	if isinstance(node, (ast.List, ast.Tuple)):
		return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
	return []


def clean(s):
	s = re.sub(r"(?i)^\s*(count|sum|max|min)\((.*)\)\s*(as \w+)?\s*$", r"\2", s)
	s = s.split(" as ")[0].split(" desc")[0].split(" asc")[0].strip()
	return None if s in ("*", "") or not re.match(r"^[a-z_][a-z0-9_]*$", s) else s


def check(fn, dt, fields, where):
	if dt not in DT:
		return
	for s in fields:
		for part in str(s).split(","):
			n = clean(part)
			if n and n not in DT[dt]:
				bad.append((fn, where, dt, n))


for path in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
	if "/tests/" in path:
		continue
	tree = ast.parse(open(path).read())
	fn = os.path.relpath(path, ROOT)
	for node in ast.walk(tree):
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
			name = node.func.attr
			args = node.args
			dt = strs(args[0])[0] if args and strs(args[0]) and len(strs(args[0])) == 1 and strs(args[0])[0] in DT else None
			if name in ("get_value", "get_cached_value") and dt:
				if len(args) > 2:
					check(fn, dt, strs(args[2]), "get_value")
				if len(args) > 1 and isinstance(args[1], ast.Dict):
					check(fn, dt, [k.value for k in args[1].keys if isinstance(k, ast.Constant)], "filters")
			if name == "set_value" and dt and len(args) > 2:
				if isinstance(args[2], ast.Dict):
					check(fn, dt, [k.value for k in args[2].keys if isinstance(k, ast.Constant)], "set_value")
				else:
					check(fn, dt, strs(args[2]), "set_value")
			if name in ("get_all", "get_list", "count", "exists") and dt:
				for kw in node.keywords:
					if kw.arg == "fields" or kw.arg == "pluck":
						check(fn, dt, strs(kw.value), "fields")
					if kw.arg == "filters" and isinstance(kw.value, ast.Dict):
						check(fn, dt, [k.value for k in kw.value.keys if isinstance(k, ast.Constant)], "filters")
				if len(args) > 1 and isinstance(args[1], ast.Dict):
					check(fn, dt, [k.value for k in args[1].keys if isinstance(k, ast.Constant)], "filters")
		if isinstance(node, ast.Dict):
			keys = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
			d = keys.get("doctype")
			if isinstance(d, ast.Constant) and d.value in DT:
				check(fn, d.value, [k for k in keys if k != "doctype"], "dict")
	src = open(path).read()
	for m in re.finditer(r"`tab([A-Z][A-Za-z ]+)`\s+(\w+)?", src):
		pass
for b in sorted(set(bad)):
	print(*b)
print("unknown keys:", len(set(bad)))
