#!/usr/bin/env python3
"""Narrow Telegram App afat flavor to arm64-v8a only (debug builds only allow afat)."""
from pathlib import Path
import re
import sys

p = Path("telegram/TMessagesProj_App/build.gradle")
if not p.exists():
    print("ERROR: TMessagesProj_App/build.gradle missing", file=sys.stderr)
    raise SystemExit(1)

t = p.read_text(encoding="utf-8")
if "a11y-fork: arm64-only" in t:
    print("Already arm64-only")
    raise SystemExit(0)

# Replace afat abiFilters block (first occurrence inside afat { ... })
t2, n = re.subn(
    r"(afat\s*\{[\s\S]*?ndk\s*\{\s*)abiFilters\s+\"armeabi-v7a\"\s*,\s*\"arm64-v8a\"\s*,\s*\"x86\"\s*,\s*\"x86_64\"",
    r'\1// a11y-fork: arm64-only\n                abiFilters "arm64-v8a"',
    t,
    count=1,
)
if n < 1:
    # broader fallback
    t2, n = re.subn(
        r'abiFilters\s+"armeabi-v7a"\s*,\s*"arm64-v8a"\s*,\s*"x86"\s*,\s*"x86_64"',
        '// a11y-fork: arm64-only\n                abiFilters "arm64-v8a"',
        t,
        count=1,
    )

if n < 1:
    print("WARN: could not patch abiFilters; building fat afat")
else:
    p.write_text(t2, encoding="utf-8")
    print("afat abiFilters -> arm64-v8a only OK")
