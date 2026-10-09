#!/usr/bin/env python3
"""Prepare unique package id + own signing key so Play Protect is less aggressive.

- Changes APP_PACKAGE away from official org.telegram.messenger
- Generates (or restores from env) a private release keystore
- Points gradle signing at that keystore
- Disables R8 minify on release
- Strips debug applicationIdSuffix .beta
- Patches google-services.json so process*GoogleServices matches new package

Env (optional GitHub Secrets):
  A11Y_KEYSTORE_BASE64  - base64 of .jks/.keystore (preferred for stable updates)
  A11Y_STORE_PASSWORD
  A11Y_KEY_ALIAS
  A11Y_KEY_PASSWORD
  A11Y_APP_PACKAGE      - default org.telegram.messenger.accessible
"""
from pathlib import Path
import base64
import copy
import json
import os
import re
import subprocess
import sys

ROOT = Path("telegram")
GP = ROOT / "gradle.properties"
KS_DIR = ROOT / "TMessagesProj" / "config"
KS_PATH = KS_DIR / "a11y-release.keystore"

DEFAULT_PACKAGE = "org.telegram.messenger.accessible"
DEFAULT_ALIAS = "a11ykey"
DEFAULT_PASS = "telegram-a11y-local"


def set_prop(text: str, key: str, value: str) -> str:
    if re.search(rf"(?m)^{re.escape(key)}=", text):
        return re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", text, count=1)
    return text.rstrip() + f"\n{key}={value}\n"


def patch_google_services(package: str) -> None:
    """Google Services plugin requires a client entry matching applicationId."""
    files = list(ROOT.rglob("google-services.json"))
    if not files:
        print("WARN: no google-services.json found")
        return
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN: skip {path}: {e}")
            continue
        clients = data.get("client") or []
        names = []
        for c in clients:
            try:
                names.append(c["client_info"]["android_client_info"]["package_name"])
            except Exception:
                pass
        if package in names:
            print(f"google-services already has {package}: {path}")
            continue
        if not clients:
            print(f"WARN: empty client list in {path}")
            continue
        # Clone first client and set our package (enough for build; FCM may be limited)
        new_c = copy.deepcopy(clients[0])
        try:
            new_c["client_info"]["android_client_info"]["package_name"] = package
        except Exception:
            print(f"WARN: cannot set package_name in {path}")
            continue
        clients.append(new_c)
        data["client"] = clients
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"google-services.json + client {package}: {path}")


def main() -> int:
    if not GP.exists():
        print("ERROR: gradle.properties missing", file=sys.stderr)
        return 1

    package = os.environ.get("A11Y_APP_PACKAGE", DEFAULT_PACKAGE).strip() or DEFAULT_PACKAGE
    store_pass = os.environ.get("A11Y_STORE_PASSWORD", DEFAULT_PASS).strip() or DEFAULT_PASS
    key_pass = os.environ.get("A11Y_KEY_PASSWORD", store_pass).strip() or store_pass
    alias = os.environ.get("A11Y_KEY_ALIAS", DEFAULT_ALIAS).strip() or DEFAULT_ALIAS
    b64 = os.environ.get("A11Y_KEYSTORE_BASE64", "").strip()

    KS_DIR.mkdir(parents=True, exist_ok=True)

    if b64:
        KS_PATH.write_bytes(base64.b64decode(b64))
        print(f"Restored keystore from A11Y_KEYSTORE_BASE64 ({KS_PATH.stat().st_size} bytes)")
    elif not KS_PATH.exists():
        cmd = [
            "keytool", "-genkeypair", "-v",
            "-keystore", str(KS_PATH),
            "-alias", alias,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", store_pass,
            "-keypass", key_pass,
            "-dname", "CN=Telegram Accessible, OU=A11y, O=TelegramA11y, L=Internet, ST=NA, C=IR",
        ]
        subprocess.check_call(cmd)
        print(f"Generated new keystore at {KS_PATH}")
        print("IMPORTANT: download keystore artifact and save as secret A11Y_KEYSTORE_BASE64 for updates.")
    else:
        print(f"Using existing keystore {KS_PATH}")

    gp = GP.read_text(encoding="utf-8")
    gp = set_prop(gp, "APP_PACKAGE", package)
    gp = set_prop(gp, "RELEASE_STORE_PASSWORD", store_pass)
    gp = set_prop(gp, "RELEASE_KEY_PASSWORD", key_pass)
    gp = set_prop(gp, "RELEASE_KEY_ALIAS", alias)
    GP.write_text(gp, encoding="utf-8")
    print(f"APP_PACKAGE={package}")

    patch_google_services(package)

    app_gradle = ROOT / "TMessagesProj_App" / "build.gradle"
    if app_gradle.exists():
        t = app_gradle.read_text(encoding="utf-8")
        old = 'storeFile file("../TMessagesProj/config/release.keystore")'
        new = 'storeFile file("../TMessagesProj/config/a11y-release.keystore") // a11y-fork unique signing'
        if old in t:
            t = t.replace(old, new)
            print("Signing path -> a11y-release.keystore OK")
        else:
            print("WARN: release.keystore path not found in App build.gradle")

        if 'applicationIdSuffix ".beta"' in t:
            t = t.replace(
                'applicationIdSuffix ".beta"',
                '// a11y-fork: no beta suffix\n            // applicationIdSuffix ".beta"',
                1,
            )
            print("Removed .beta applicationIdSuffix OK")

        if "a11y-fork: release no minify" not in t:
            t2, n = re.subn(
                r"(release\s*\{[\s\S]*?)minifyEnabled\s+true",
                r"\1// a11y-fork: release no minify\n            minifyEnabled false",
                t,
                count=1,
            )
            if n:
                t = t2
                print("release minifyEnabled -> false OK")
            else:
                print("WARN: could not disable release minifyEnabled")

        app_gradle.write_text(t, encoding="utf-8")
    else:
        print("WARN: TMessagesProj_App/build.gradle missing")

    print("prepare-release-signing done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
