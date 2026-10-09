#!/usr/bin/env python3
import os
import re
import pathlib
import sys

p = pathlib.Path("telegram/TMessagesProj/src/main/java/org/telegram/messenger/BuildVars.java")
if not p.exists():
    print("ERROR: BuildVars.java missing", file=sys.stderr)
    raise SystemExit(1)

t = p.read_text(encoding="utf-8")
api_id = os.environ.get("API_ID", "").strip()
api_hash = os.environ.get("API_HASH", "").strip()

if not api_id or not api_hash:
    print("ERROR: API_ID or API_HASH environment variable is missing", file=sys.stderr)
    raise SystemExit(1)

t2, n1 = re.subn(r"(APP_ID\s*=\s*)[^;\n]+", r"\g<1>" + api_id, t, count=1)
t2, n2 = re.subn(r'(APP_HASH\s*=\s*)"[^"]*"', r'\g<1>"' + api_hash + '"', t2, count=1)

if n1 < 1 or n2 < 1:
    raise SystemExit(f"Could not patch BuildVars (id={n1}, hash={n2})")

p.write_text(t2, encoding="utf-8")
print("BuildVars patched OK")