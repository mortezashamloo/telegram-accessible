#!/usr/bin/env python3
"""Apply accessibility patches to cloned Telegram tree (12.10.6 baseline) (cwd parent of telegram/).

Step 0 applies scripts/mehran-a11y.patch: the accessibility work of the
mehranlatifi83/Telegram fork (12.10.5 release), MINUS its download/upload percentage
announcement (this project has its own) and MINUS its GitHub self-updater. Everything
else in this file then runs on top of it.

This revision is intentionally based on v10 in full. It preserves v10 patches and only
adds the requested small-file 3-state setting, exact progress steps, fresh-install
auto-download OFF defaults, and private-chat support for Go to first message.

Portable: works with GitHub Actions (patches-repo/scripts) or local kit (scripts/).
When DrKLO/Telegram updates, re-run this script on a fresh clone.
"""
from pathlib import Path
import re
import html
import shutil
import sys
import wave
import struct
import math

ROOT = Path("telegram/TMessagesProj")
RES = ROOT / "src/main/res"
JAVA = ROOT / "src/main/java"


def _find_scripts_dir() -> Path:
    for cand in (
        Path("patches-repo/scripts"),
        Path("scripts"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "A11yConfig.java").exists() or (cand / "apply-a11y.py").exists():
            return cand
    return Path("scripts")


SCRIPTS = _find_scripts_dir()

FA_NAME = "\u062a\u0644\u06af\u0631\u0627\u0645 \u062f\u0633\u062a\u0631\u0633\u200c\u067e\u0630\u06cc\u0631"
EN_NAME = "Telegram Accessible"

OPTION_FORWARD_NO_QUOTE = 200
OPTION_REACTIONS_MENU = 201
OPTION_FORWARD_TO_SAVED = 202
OPTION_SELECT_MESSAGE = 203
OPTION_LEAVE_COMMENT = 204
OPTION_BOT_BUTTONS_MENU = 205
OPTION_LINKS_MENU = 206
OPTION_FORWARD_HERE = 220


def apply_mehran_patch() -> None:
    """Apply the bundled accessibility patch of the mehranlatifi83/Telegram fork.

    It was produced against upstream 12.10.6 (f2908b14) and touches only
    TMessagesProj/src/main. If upstream has moved far enough for hunks to no longer
    apply, this stops the build with a clear message instead of producing an app that
    silently lacks half of the features.
    """
    import subprocess
    import os
    patch = SCRIPTS / "mehran-a11y.patch"
    if os.environ.get("A11Y_SKIP_MEHRAN") == "1":
        print("A11Y_SKIP_MEHRAN=1 -- building with our own project only")
        return
    if not patch.exists():
        print("mehran-a11y.patch not found -- building with our own project only")
        return
    marker = Path("telegram/.a11y-mehran-applied")
    if marker.exists():
        print("mehran-a11y.patch already applied")
        return
    patch = patch.resolve()
    chk = subprocess.run(["git", "apply", "--check", "-p1", "--whitespace=nowarn", str(patch)],
                         cwd="telegram", capture_output=True, text=True)
    if chk.returncode == 0:
        r = subprocess.run(["git", "apply", "-p1", "--whitespace=nowarn", str(patch)],
                           cwd="telegram", capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout + r.stderr, file=sys.stderr)
            raise SystemExit("ERROR: mehran-a11y.patch failed to apply")
        print("mehran-a11y.patch applied cleanly (git apply)")
    else:
        # upstream moved a little: let `patch` apply what it can with fuzz, and refuse on rejects
        r = subprocess.run(["patch", "-p1", "--forward", "-F3", "--no-backup-if-mismatch", "-i", str(patch)],
                           cwd="telegram", capture_output=True, text=True)
        rejects = [str(x) for x in Path("telegram").rglob("*.rej")]
        if r.returncode != 0 or rejects:
            print(chk.stderr[:3000], file=sys.stderr)
            print(r.stdout[-3000:], file=sys.stderr)
            raise SystemExit(
                "ERROR: upstream Telegram changed too much for mehran-a11y.patch (%d rejected hunks: %s). "
                "Pin the clone to the tested commit f2908b14 or regenerate the patch." % (len(rejects), ", ".join(rejects[:5])))
        print("mehran-a11y.patch applied with fuzz (patch -F3)")
    marker.write_text("ok\n")



def _set_string(path: Path, name: str, value: str) -> None:
    # Android string resources are XML. Escape XML text characters before
    # writing/updating a <string> element. In particular, "&" in labels such
    # as "Progress & voice quality" must be written as "&amp;".
    value = html.escape(value, quote=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<resources>\n"
            f'    <string name="{name}">{value}</string>\n'
            "</resources>\n",
            encoding="utf-8",
        )
        return
    t = path.read_text(encoding="utf-8")
    if f'name="{name}"' in t:
        t2, _ = re.subn(
            rf'(<string\s+name="{name}">)[^<]*(</string>)',
            rf"\1{value}\2",
            t,
            count=1,
        )
        path.write_text(t2, encoding="utf-8")
    else:
        path.write_text(
            t.replace(
                "</resources>",
                f'    <string name="{name}">{value}</string>\n</resources>',
            ),
            encoding="utf-8",
        )


def patch_app_name() -> None:
    p = RES / "values/strings.xml"
    if p.exists():
        _set_string(p, "AppName", EN_NAME)
        _set_string(p, "AppNameBeta", EN_NAME)
    for rel in ("values-fa/strings.xml", "values-fa-rIR/strings.xml"):
        _set_string(RES / rel, "AppName", FA_NAME)
        _set_string(RES / rel, "AppNameBeta", FA_NAME)
    print("AppName OK")



def _patch_a11y_string_resources() -> None:
    """Install every accessibility-fork string resource referenced by A11yConfig.java.

    The previous build failed because A11yConfig referenced the
    Label/Title/On/Off resource names while the installer created only
    shorter alias names. Keep both the exact names and compatibility aliases.
    """
    en = {
        "A11yAccessibleSettingsTitle": "Accessible settings",
        "A11yProgressAnnounceLabel": "Progress announce: %s",
        "A11yProgressStepLabel": "Progress step %1$d percent",
        "A11yProgressStepPickerTitle": "Progress announce step",
        "A11yVoiceQualityLabel": "Voice quality: %s",
        "A11yVoiceQualityPickerTitle": "Voice message quality",
        "A11yVoiceLow": "Low",
        "A11yVoiceMedium": "Medium",
        "A11yVoiceHigh": "High",
        "A11yHideSponsorLabel": "Hide sponsor channel: %s",
        "A11ySponsorHidden": "Sponsor channel hidden",
        "A11ySponsorShown": "Sponsor channel shown",
        "A11yGhostModeLabel": "Ghost mode: %s",
        "A11yGhostOn": "Ghost mode on",
        "A11yGhostOff": "Ghost mode off",
        "A11yStatusPreviewLabel": "Show status in preview: %s",
        "A11yStatusOn": "Status preview on",
        "A11yStatusOff": "Status preview off",
        "A11yForwardSavedNoQuoteLabel": "Forward to Saved Messages with no quote: %s",
        "A11yRecordingBeepLabel": "Recording start beep: %s",
        "A11ySolarCalendarLabel": "Solar calendar: %s",
        "A11yBlockSmallFilesLabel": "Do not auto-download small files: %s",
        "A11yNoAutoDownloadLabel": "Do not auto-download files: %s",
        "A11yVoiceOnlyAutoDownloadLabel": "Do not auto-download files except voice messages: %s",
        "A11yOn": "On", "A11yOff": "Off", "A11yCancel": "Cancel",
        "A11ySolarDate": "%1$s",
        "A11yAt": "at",
        "A11yAccessibleSettings": "Accessible settings",
        "A11yProgressAnnounce": "Progress announce",
        "A11yVoiceQuality": "Voice quality",
        "A11yProgressAnnounceSummary": "Progress & voice quality",
        "A11yProgressAnnounceStep": "Progress announce step",
        "A11yVoiceMessageQuality": "Voice message quality",
        "A11yLow": "Low", "A11yMedium": "Medium", "A11yHigh": "High",
        "A11yProgressStep": "Progress step %1$d percent",
        "A11yVoiceQualitySelected": "Voice quality %1$s",
        "A11yForwardWithoutQuote": "Forward without quote",
        "A11yForwardToSaved": "Forward to Saved Messages",
        "A11yForwardedToSaved": "Forwarded to Saved Messages",
        "A11ySelected": "Selected", "A11yReceiveAt": "received at %1$s",
        "A11ySentAt": "sent at %1$s", "A11yBotButtons": "Bot Buttons",
        "A11yGoToFirstMessage": "Go to first message",
        "A11yLinks": "Links", "A11yLinksLabel": "Links: %s", "A11yNoLinks": "No links",
        "A11yBotNumber": "Bot %1$d",
        "A11yPercent": "%1$d percent",
        "A11yDownloaded": "Downloaded",
        "A11yDownloadStateLabel": "Downloaded / not downloaded status: %s",
        "A11yAlbumReadingLabel": "Announce media album grouping: %s",
        "A11yAlbumReadingSummary": "Screen reader announces when a message belongs to an album and its position",
        "A11yAdminTagLabel": "Announce admin and group tags: %s",
        "A11yAdminTagSummary": "Adds admin, owner or the group’s own tag after the sender name in groups.",
        "A11yLeaveComment": "Leave comment",
        "A11yCommentOne": "1 comment",
        "A11yCommentsCount": "%1$d comments",
        "A11yUserStatusLabel": "User status announcements (typing, recording, online): %s",
        "A11yChatOpenSoundLabel": "Touch sound when a chat opens and when a message is tapped: %s",
        "A11ySenderOptionsLabel": "Sender options in message menu: %s",
        "A11yVoiceShareSaveLabel": "Share and save to music for voice messages: %s",
        "A11yPlayerSeekLabel": "Rewind and forward in audio player: %s",
        "A11yPlayerRewind": "Rewind 10 seconds",
        "A11yPlayerForward": "Forward 10 seconds",
        "A11yProxyButtonLabel": "Proxy button in the chat list toolbar: %s",
        "A11yOldMenuLabel": "Old-style main menu instead of the bottom tabs: %s",
        "A11yMainMenu": "Main menu",
        "A11yCategoryLabel": "Chat category filter in the chat list: %s",
        "A11yForwardHere": "Forward here",
        "A11yForwardHereLabel": "Forward here in message options: %s",
        "A11yForwardedHere": "Forwarded here",
        "A11yCategoryButton": "Category: %s",
        "A11yCategoryPrivate": "Private chats",
        "A11yCategoryShowing": "Showing: %s",
        "A11yCategoryUnread": "Unread chats",
        "A11yMenuStyleLabel": "Main menu style: %s",
        "A11yMenuStylePickerTitle": "Main menu style",
        "A11yMenuStyleCurrent": "Current Telegram (bottom tabs)",
        "A11yMenuStyleOld": "Old-style popup menu (no bottom tabs)",
        "A11yMenuStyleDrawer": "Use legacy navigation drawer (no bottom tabs)",
        "A11yLegacyDrawerRestart": "Close and reopen the app to apply",
        "A11yCategoryRead": "Read chats",
        "A11yUnselected": "Unselected",
        "A11ySelectAllDone": "%1$d chats selected",
        "A11yMutualContact": "Mutual contact",
        "A11ySwitchAccount": "Switch account",
        "A11yVideoSettings": "Video settings: quality and speed",
        "A11yAddMembersConfirm": "Add selected members",
        "A11yClose": "Close",
        "A11yFileLabel": "File",
    }
    fa = {
        "A11yAccessibleSettingsTitle": "تنظیمات دسترس‌پذیری",
        "A11yProgressAnnounceLabel": "اعلام پیشرفت: %s",
        "A11yProgressStepLabel": "گام پیشرفت %1$d درصد",
        "A11yProgressStepPickerTitle": "گام اعلام پیشرفت",
        "A11yVoiceQualityLabel": "کیفیت صدا: %s",
        "A11yVoiceQualityPickerTitle": "کیفیت پیام صوتی",
        "A11yVoiceLow": "پایین", "A11yVoiceMedium": "متوسط", "A11yVoiceHigh": "بالا",
        "A11yHideSponsorLabel": "مخفی کردن کانال حامی: %s",
        "A11ySponsorHidden": "کانال حامی مخفی شد",
        "A11ySponsorShown": "کانال حامی نمایش داده شد",
        "A11yGhostModeLabel": "حالت روح: %s",
        "A11yGhostOn": "حالت روح روشن شد", "A11yGhostOff": "حالت روح خاموش شد",
        "A11yStatusPreviewLabel": "نمایش وضعیت در پیش‌نمایش: %s",
        "A11yStatusOn": "نمایش وضعیت روشن شد", "A11yStatusOff": "نمایش وضعیت خاموش شد",
        "A11yForwardSavedNoQuoteLabel": "فوروارد به پیام‌های ذخیره‌شده بدون نقل‌قول: %s",
        "A11yRecordingBeepLabel": "بوق شروع ضبط: %s",
        "A11ySolarCalendarLabel": "تقویم خورشیدی: %s",
        "A11yBlockSmallFilesLabel": "دانلود خودکار فایل‌های کم‌حجم را متوقف کن: %s",
        "A11yNoAutoDownloadLabel": "دانلود خودکار هیچ فایلی: %s",
        "A11yVoiceOnlyAutoDownloadLabel": "دانلود خودکار فایل‌ها به‌جز پیام‌های صوتی: %s",
        "A11yOn": "روشن", "A11yOff": "خاموش", "A11yCancel": "لغو",
        "A11ySolarDate": "%1$s",
        "A11yAt": "در",
        "A11yAccessibleSettings": "تنظیمات دسترس‌پذیری",
        "A11yProgressAnnounce": "اعلام پیشرفت", "A11yVoiceQuality": "کیفیت صدا",
        "A11yProgressAnnounceSummary": "اعلام پیشرفت و کیفیت صدا",
        "A11yProgressAnnounceStep": "گام اعلام پیشرفت", "A11yVoiceMessageQuality": "کیفیت پیام صوتی",
        "A11yLow": "پایین", "A11yMedium": "متوسط", "A11yHigh": "بالا",
        "A11yProgressStep": "گام پیشرفت %1$d درصد",
        "A11yVoiceQualitySelected": "کیفیت صدا %1$s",
        "A11yForwardWithoutQuote": "فوروارد بدون نقل‌قول",
        "A11yForwardToSaved": "ارسال به پیام‌های ذخیره‌شده",
        "A11yForwardedToSaved": "به پیام‌های ذخیره‌شده ارسال شد", "A11ySelected": "انتخاب شد",
        "A11yReceiveAt": "دریافت در ساعت %1$s", "A11ySentAt": "ارسال در ساعت %1$s",
        "A11yBotButtons": "دکمه‌های ربات", "A11yGoToFirstMessage": "رفتن به اولین پیام",
        "A11yLinks": "لینک‌ها", "A11yLinksLabel": "لینک‌ها: %s", "A11yNoLinks": "لینکی وجود ندارد",
        "A11yBotNumber": "ربات %1$d", "A11yPercent": "%1$d درصد",
        "A11yDownloaded": "دانلود شد",
        "A11yDownloadStateLabel": "وضعیت دانلود‌شده / دانلود‌نشده: %s",
        "A11yAlbumReadingLabel": "اعلام گروه‌بندی آلبوم رسانه: %s",
        "A11yAlbumReadingSummary": "صفحه‌خوان اعلام می‌کند که پیام جزو یک آلبوم است و جایگاه آن را می‌گوید",
        "A11yAdminTagLabel": "اعلام تگ ادمین و گروه: %s",
        "A11yAdminTagSummary": "تگ ادمین، مالک یا تگ اختصاصی گروه را بعد از نام فرستنده در گروه‌ها اضافه می‌کند.",
        "A11yLeaveComment": "ثبت نظر",
        "A11yCommentOne": "1 نظر",
        "A11yCommentsCount": "%1$d نظر",
        "A11yUserStatusLabel": "اعلام وضعیت کاربر (در حال تایپ، ضبط ویس، آنلاین): %s",
        "A11yChatOpenSoundLabel": "صدای لمس هنگام باز شدن چت و ضربه روی پیام: %s",
        "A11ySenderOptionsLabel": "گزینه‌های فرستنده در منوی پیام: %s",
        "A11yVoiceShareSaveLabel": "اشتراک‌گذاری و ذخیره در موسیقی برای پیام‌های صوتی: %s",
        "A11yPlayerSeekLabel": "عقب و جلو در پخش‌کننده‌ی صدا: %s",
        "A11yPlayerRewind": "۱۰ ثانیه عقب",
        "A11yPlayerForward": "۱۰ ثانیه جلو",
        "A11yProxyButtonLabel": "دکمه‌ی پروکسی در نوار بالای لیست چت: %s",
        "A11yOldMenuLabel": "منوی قدیمی تلگرام به‌جای نوار پایین: %s",
        "A11yMainMenu": "منوی اصلی",
        "A11yCategoryLabel": "فیلتر دسته‌بندی چت‌ها در لیست چت: %s",
        "A11yForwardHere": "فوروارد همین‌جا",
        "A11yForwardHereLabel": "فوروارد همین‌جا در گزینه‌های پیام: %s",
        "A11yForwardedHere": "پیام دوباره در همین گفتگو ارسال شد",
        "A11yCategoryButton": "دسته‌بندی: %s",
        "A11yCategoryPrivate": "گفتگوهای خصوصی",
        "A11yCategoryShowing": "نمایش: %s",
        "A11yCategoryUnread": "گفتگوهای خوانده‌نشده",
        "A11yMenuStyleLabel": "سبک منوی اصلی: %s",
        "A11yMenuStylePickerTitle": "سبک منوی اصلی",
        "A11yMenuStyleCurrent": "تلگرام فعلی (نوار پایین)",
        "A11yMenuStyleOld": "منوی بازشوی قدیمی (بدون نوار پایین)",
        "A11yMenuStyleDrawer": "استفاده از منوی کشویی قدیمی (بدون نوار پایین)",
        "A11yLegacyDrawerRestart": "برای اعمال، برنامه را کامل ببندید و دوباره باز کنید",
        "A11yCategoryRead": "گفتگوهای خوانده‌شده",
        "A11yUnselected": "از انتخاب خارج شد",
        "A11ySelectAllDone": "%1$d گفتگو انتخاب شد",
        "A11yMutualContact": "مخاطب دوطرفه",
        "A11ySwitchAccount": "تعویض حساب",
        "A11yVideoSettings": "تنظیمات ویدیو: کیفیت و سرعت",
        "A11yAddMembersConfirm": "افزودن اعضای انتخاب‌شده",
        "A11yClose": "بستن",
        "A11yFileLabel": "فایل",
        "AccDescrShareInChats_one": "اشتراک‌گذاری در %1$d گفتگو",
        "AccDescrShareInChats_other": "اشتراک‌گذاری در %1$d گفتگو",
    }
    for rel, values in (("values/strings.xml", en), ("values-fa/strings.xml", fa), ("values-fa-rIR/strings.xml", fa)):
        path = RES / rel
        if not path.exists():
            print("WARN: resource file missing:", path)
            continue
        for name, value in values.items():
            _set_string(path, name, value)


def patch_a11y_localization() -> None:
    """Replace accessibility-fork hard-coded runtime text with localized resources."""
    _patch_a11y_string_resources()

    # A11yConfig.java is copied from the user's repository. Localize its labels
    # without replacing or removing any of the existing settings/features.
    cfg = JAVA / "org/telegram/messenger/A11yConfig.java"
    if cfg.exists():
        t = cfg.read_text(encoding="utf-8")
        replacements = {
            'return "Low";': 'return LocaleController.getString(R.string.A11yLow);',
            'return "Medium";': 'return LocaleController.getString(R.string.A11yMedium);',
            'return "High";': 'return LocaleController.getString(R.string.A11yHigh);',
            '"Progress announce: " + progressStepLabel()': 'LocaleController.getString(R.string.A11yProgressAnnounce) + ": " + progressStepLabel()',
            '"Voice quality: " + voiceQualityLabel()': 'LocaleController.getString(R.string.A11yVoiceQuality) + ": " + voiceQualityLabel()',
            '"Accessible settings"': 'LocaleController.getString(R.string.A11yAccessibleSettings)',
            '"Progress announce step"': 'LocaleController.getString(R.string.A11yProgressAnnounceStep)',
            '"Voice message quality"': 'LocaleController.getString(R.string.A11yVoiceMessageQuality)',
            '"Progress step " + steps[which] + " percent"': 'LocaleController.formatString("A11yProgressStep", R.string.A11yProgressStep, steps[which])',
            '"Voice quality " + labels[which]': 'LocaleController.formatString("A11yVoiceQualitySelected", R.string.A11yVoiceQualitySelected, labels[which])',
        }
        changed = False
        for old, new in replacements.items():
            if old in t:
                t = t.replace(old, new)
                changed = True
        if changed:
            cfg.write_text(t, encoding="utf-8")
            print("A11yConfig localization OK")

    targets = [
        JAVA / "org/telegram/ui/ChatActivity.java",
        JAVA / "org/telegram/ui/Cells/DialogCell.java",
        JAVA / "org/telegram/ui/Components/RadialProgress.java",
        JAVA / "org/telegram/ui/Components/RadialProgress2.java",
        JAVA / "org/telegram/ui/SettingsActivity.java",
    ]
    for path in targets:
        if not path.exists():
            continue
        t = path.read_text(encoding="utf-8")
        original = t
        replacements = {
            'items.add("Forward without quote");': 'items.add(LocaleController.getString(R.string.A11yForwardWithoutQuote));',
            'items.add("Forward to Saved Messages");': 'items.add(LocaleController.getString(R.string.A11yForwardToSaved));',
            'announceForAccessibility("Forwarded to Saved Messages");': 'announceForAccessibility(LocaleController.getString(R.string.A11yForwardedToSaved));',
            'announceForAccessibility("Selected");': 'announceForAccessibility(LocaleController.getString(R.string.A11ySelected));',
            'sb.append(message.isOut() ? "sent @" : "receive @");': 'sb.append(LocaleController.formatString(message.isOut() ? "A11ySentAt" : "A11yReceiveAt", message.isOut() ? R.string.A11ySentAt : R.string.A11yReceiveAt, a11yClockTime));',
            'items.add("Bot Buttons");': 'items.add(LocaleController.getString(R.string.A11yBotButtons));',
            'items.add("Links");': 'items.add(LocaleController.getString(R.string.A11yLinks));',
            'botBtnBuilder.setTitle("Bot Buttons");': 'botBtnBuilder.setTitle(LocaleController.getString(R.string.A11yBotButtons));',
            '("Bot " + (labels.size() + 1))': 'LocaleController.formatString("A11yBotNumber", R.string.A11yBotNumber, labels.size() + 1)',
            '"Accessible settings", "Progress & voice quality"': 'LocaleController.getString(R.string.A11yAccessibleSettings), LocaleController.getString(R.string.A11yProgressAnnounceSummary)',
            'parent.announceForAccessibility(org.telegram.messenger.LocaleController.formatString("A11yPercent", org.telegram.messenger.R.string.A11yPercent, step));': 'parent.announceForAccessibility(org.telegram.messenger.LocaleController.formatString("A11yPercent", org.telegram.messenger.R.string.A11yPercent, step));',
        }
        for old, new in replacements.items():
            t = t.replace(old, new)
        if t != original:
            path.write_text(t, encoding="utf-8")
            print(f"{path.name} localization OK")

    print("A11y English/Persian localization OK")

def install_a11y_config() -> None:
    src = SCRIPTS / "A11yConfig.java"
    dst = JAVA / "org/telegram/messenger/A11yConfig.java"
    if not src.exists():
        print("WARN: A11yConfig.java missing in", SCRIPTS)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    cfg = dst.read_text(encoding="utf-8")
    # a11y-fork: Solar calendar is ON by default (can be turned off from Accessible Settings).
    # The recording-start beep stays OFF by default (A11yConfig.java's own default); the
    # recording vibration (patch_recording_beep) is unconditional and independent of it.
    if "PREF_LINKS_MENU" not in cfg:
        cfg = cfg.replace(
            'public static final String PREF_SOLAR_CALENDAR = "a11y_solar_calendar";',
            'public static final String PREF_SOLAR_CALENDAR = "a11y_solar_calendar";\n    public static final String PREF_LINKS_MENU = "a11y_links_menu";'
        )
    if "getLinksMenuEnabled()" not in cfg:
        anchor = "    public static boolean getSolarCalendar() {"
        methods = (
            "    public static boolean getLinksMenuEnabled() {\n"
            "        try {\n"
            "            return MessagesController.getGlobalMainSettings().getBoolean(PREF_LINKS_MENU, false);\n"
            "        } catch (Throwable ignore) {\n"
            "            return false;\n"
            "        }\n"
            "    }\n\n"
            "    public static void setLinksMenuEnabled(boolean value) {\n"
            "        try {\n"
            "            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_LINKS_MENU, value).apply();\n"
            "        } catch (Throwable ignore) {\n"
            "        }\n"
            "    }\n\n"
        )
        if anchor in cfg:
            cfg = cfg.replace(anchor, methods + anchor, 1)
    # a11y-fork: Solar date replacement supports both old int and current long signatures.
    # It is date-only: Telegram's surrounding formatter controls the time-of-day.
    solar_start = cfg.find("    public static String formatSolarDate(")
    if solar_start >= 0:
        solar_end = cfg.find("    private static String toPersianDigits", solar_start)
        if solar_end > solar_start:
            solar_method = (
                "    public static String formatSolarDate(long unixSeconds) {\n"
                "        try {\n"
                "            java.util.Calendar cal = java.util.Calendar.getInstance();\n"
                "            cal.setTimeInMillis(unixSeconds * 1000L);\n"
                "            int gy = cal.get(java.util.Calendar.YEAR);\n"
                "            int gm = cal.get(java.util.Calendar.MONTH) + 1;\n"
                "            int gd = cal.get(java.util.Calendar.DAY_OF_MONTH);\n"
                "            int jy;\n"
                "            if (gy > 1600) { jy = 979; gy -= 1600; } else { jy = 0; gy -= 621; }\n"
                "            int[] gdm = {0,31,59,90,120,151,181,212,243,273,304,334};\n"
                "            int gy2 = gm > 2 ? gy + 1 : gy;\n"
                "            int days = 365 * gy + (gy2 + 3) / 4 - (gy2 + 99) / 100 + (gy2 + 399) / 400 - 80 + gd + gdm[gm - 1];\n"
                "            jy += 33 * (days / 12053); days %= 12053;\n"
                "            jy += 4 * (days / 1461); days %= 1461;\n"
                "            if (days > 365) { jy += (days - 1) / 365; days = (days - 1) % 365; }\n"
                "            int jm = days < 186 ? 1 + days / 31 : 7 + (days - 186) / 30;\n"
                "            int jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);\n"
                "            String[] faMonths = {\"فروردین\",\"اردیبهشت\",\"خرداد\",\"تیر\",\"مرداد\",\"شهریور\",\"مهر\",\"آبان\",\"آذر\",\"دی\",\"بهمن\",\"اسفند\"};\n"
                "            String[] enMonths = {\"Farvardin\",\"Ordibehesht\",\"Khordad\",\"Tir\",\"Mordad\",\"Shahrivar\",\"Mehr\",\"Aban\",\"Azar\",\"Dey\",\"Bahman\",\"Esfand\"};\n"
                "            boolean isFa = \"fa\".equalsIgnoreCase(java.util.Locale.getDefault().getLanguage());\n"
                "            String month = (isFa ? faMonths : enMonths)[jm - 1];\n"
                "            java.util.Calendar now = java.util.Calendar.getInstance();\n"
                "            int nowGy = now.get(java.util.Calendar.YEAR);\n"
                "            int nowGm = now.get(java.util.Calendar.MONTH) + 1;\n"
                "            int nowGd = now.get(java.util.Calendar.DAY_OF_MONTH);\n"
                "            int nowJy;\n"
                "            if (nowGy > 1600) { nowJy = 979; nowGy -= 1600; } else { nowJy = 0; nowGy -= 621; }\n"
                "            int nowGy2 = nowGm > 2 ? nowGy + 1 : nowGy;\n"
                "            int nowDays = 365 * nowGy + (nowGy2 + 3) / 4 - (nowGy2 + 99) / 100 + (nowGy2 + 399) / 400 - 80 + nowGd + gdm[nowGm - 1];\n"
                "            nowJy += 33 * (nowDays / 12053); nowDays %= 12053;\n"
                "            nowJy += 4 * (nowDays / 1461); nowDays %= 1461;\n"
                "            if (nowDays > 365) { nowJy += (nowDays - 1) / 365; }\n"
                "            String value = jy == nowJy ? String.format(java.util.Locale.US, \"%d %s\", jd, month) : String.format(java.util.Locale.US, \"%d %s %d\", jd, month, jy);\n"
                "            return LocaleController.formatString(R.string.A11ySolarDate, isFa ? toPersianDigits(value) : value);\n"
                "        } catch (Throwable ignore) { return \"\"; }\n"
                "    }\n\n"
                "    public static String formatSolarDateAudio(long unixSeconds) {\n"
                "        try {\n"
                "            long dateMs = unixSeconds * 1000L;\n"
                "            java.util.Calendar now = java.util.Calendar.getInstance();\n"
                "            java.util.Calendar msg = java.util.Calendar.getInstance();\n"
                "            msg.setTimeInMillis(dateMs);\n"
                "            int nowDay = now.get(java.util.Calendar.DAY_OF_YEAR);\n"
                "            int nowYear = now.get(java.util.Calendar.YEAR);\n"
                "            int msgDay = msg.get(java.util.Calendar.DAY_OF_YEAR);\n"
                "            int msgYear = msg.get(java.util.Calendar.YEAR);\n"
                "            java.text.SimpleDateFormat timeFmt = new java.text.SimpleDateFormat(\"HH:mm\", java.util.Locale.getDefault());\n"
                "            String time = timeFmt.format(new java.util.Date(dateMs));\n"
                "            if (msgDay == nowDay && msgYear == nowYear) {\n"
                "                return LocaleController.formatString(R.string.TodayAtFormatted, time);\n"
                "            } else if (msgDay + 1 == nowDay && msgYear == nowYear) {\n"
                "                return LocaleController.formatString(R.string.YesterdayAtFormatted, time);\n"
                "            } else {\n"
                "                String solar = formatSolarDate(unixSeconds);\n"
                "                if (solar == null || solar.isEmpty()) return LocaleController.formatDateAudio(unixSeconds, true);\n"
                "                return solar + \" \" + LocaleController.getString(R.string.A11yAt) + \" \" + time;\n"
                "            }\n"
                "        } catch (Throwable ignore) {\n"
                "            return LocaleController.formatDateAudio(unixSeconds, true);\n"
                "        }\n"
                "    }\n\n"
            )
            cfg = cfg[:solar_start] + solar_method + cfg[solar_end:]
    # a11y-fork: Solar Hijri for chat date separators, mirroring Telegram's own
    # LocaleController.formatDateChat(date, checkYear) short/full-year decision exactly.
    # Self-contained (own Jalali maths + digit conversion) so it does not depend on which
    # helpers the user's A11yConfig.java happens to contain.
    if "formatSolarDateChat(" not in cfg:
        chat_method = (
            "    // a11y-fork: solar formatDateChat\n"
            "    public static String formatSolarDateChat(long unixSeconds, boolean checkYear) {\n"
            "        try {\n"
            "            long dateMs = unixSeconds * 1000L;\n"
            "            java.util.Calendar msg = java.util.Calendar.getInstance();\n"
            "            msg.setTimeInMillis(dateMs);\n"
            "            int[] j = a11yGregorianToJalali(msg.get(java.util.Calendar.YEAR), msg.get(java.util.Calendar.MONTH) + 1, msg.get(java.util.Calendar.DAY_OF_MONTH));\n"
            "            boolean shortForm;\n"
            "            if (checkYear) {\n"
            "                shortForm = java.util.Calendar.getInstance().get(java.util.Calendar.YEAR) == msg.get(java.util.Calendar.YEAR);\n"
            "            } else {\n"
            "                shortForm = Math.abs(System.currentTimeMillis() - dateMs) < 31536000000L;\n"
            "            }\n"
            "            java.util.Locale loc = null;\n"
            "            try { loc = LocaleController.getInstance().getCurrentLocale(); } catch (Throwable ignore) {}\n"
            "            if (loc == null) loc = java.util.Locale.getDefault();\n"
            "            boolean isFa = \"fa\".equalsIgnoreCase(loc.getLanguage());\n"
            "            String[] faMonths = {\"\\u0641\\u0631\\u0648\\u0631\\u062f\\u06cc\\u0646\",\"\\u0627\\u0631\\u062f\\u06cc\\u0628\\u0647\\u0634\\u062a\",\"\\u062e\\u0631\\u062f\\u0627\\u062f\",\"\\u062a\\u06cc\\u0631\",\"\\u0645\\u0631\\u062f\\u0627\\u062f\",\"\\u0634\\u0647\\u0631\\u06cc\\u0648\\u0631\",\"\\u0645\\u0647\\u0631\",\"\\u0622\\u0628\\u0627\\u0646\",\"\\u0622\\u0630\\u0631\",\"\\u062f\\u06cc\",\"\\u0628\\u0647\\u0645\\u0646\",\"\\u0627\\u0633\\u0641\\u0646\\u062f\"};\n"
            "            String[] enMonths = {\"Farvardin\",\"Ordibehesht\",\"Khordad\",\"Tir\",\"Mordad\",\"Shahrivar\",\"Mehr\",\"Aban\",\"Azar\",\"Dey\",\"Bahman\",\"Esfand\"};\n"
            "            String month = (isFa ? faMonths : enMonths)[j[1] - 1];\n"
            "            String value = shortForm\n"
            "                    ? j[2] + \" \" + month\n"
            "                    : j[2] + \" \" + month + (isFa ? \"\\u060c \" : \", \") + j[0];\n"
            "            if (isFa) {\n"
            "                StringBuilder sb = new StringBuilder(value.length());\n"
            "                for (int i = 0; i < value.length(); i++) {\n"
            "                    char c = value.charAt(i);\n"
            "                    sb.append(c >= '0' && c <= '9' ? (char) ('\\u06f0' + (c - '0')) : c);\n"
            "                }\n"
            "                value = sb.toString();\n"
            "            }\n"
            "            return value;\n"
            "        } catch (Throwable ignore) {\n"
            "            return \"\";\n"
            "        }\n"
            "    }\n\n"
            "    private static int[] a11yGregorianToJalali(int gy, int gm, int gd) {\n"
            "        int jy;\n"
            "        if (gy > 1600) { jy = 979; gy -= 1600; } else { jy = 0; gy -= 621; }\n"
            "        int[] gdm = {0,31,59,90,120,151,181,212,243,273,304,334};\n"
            "        int gy2 = gm > 2 ? gy + 1 : gy;\n"
            "        int days = 365 * gy + (gy2 + 3) / 4 - (gy2 + 99) / 100 + (gy2 + 399) / 400 - 80 + gd + gdm[gm - 1];\n"
            "        jy += 33 * (days / 12053); days %= 12053;\n"
            "        jy += 4 * (days / 1461); days %= 1461;\n"
            "        if (days > 365) { jy += (days - 1) / 365; days = (days - 1) % 365; }\n"
            "        int jm = days < 186 ? 1 + days / 31 : 7 + (days - 186) / 30;\n"
            "        int jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);\n"
            "        return new int[]{jy, jm, jd};\n"
            "    }\n"
        )
        last_brace = cfg.rstrip().rfind("}")
        if last_brace > 0:
            cfg = cfg[:last_brace] + "\n" + chat_method + cfg[last_brace:]
        else:
            print("WARN: could not append formatSolarDateChat to A11yConfig.java")
    # a11y-fork: decide Persian digits/month names from Telegram's OWN selected language, not the
    # phone's system language (a Persian Telegram on an English phone otherwise got English month
    # names and Latin digits in the Solar date).
    if "a11yIsPersianUi()" not in cfg:
        cfg = cfg.replace('"fa".equalsIgnoreCase(java.util.Locale.getDefault().getLanguage())', "a11yIsPersianUi()")
        cfg = cfg.replace('"fa".equalsIgnoreCase(locale.getLanguage())', "a11yIsPersianUi()")
        helper = (
            "    // a11y-fork: Telegram's selected UI language, falling back to the system locale\n"
            "    private static boolean a11yIsPersianUi() {\n"
            "        try {\n"
            "            java.util.Locale loc = LocaleController.getInstance().getCurrentLocale();\n"
            "            if (loc == null) loc = java.util.Locale.getDefault();\n"
            "            return \"fa\".equalsIgnoreCase(loc.getLanguage());\n"
            "        } catch (Throwable ignore) {\n"
            "            return \"fa\".equalsIgnoreCase(java.util.Locale.getDefault().getLanguage());\n"
            "        }\n"
            "    }\n\n"
        )
        anchor = "    private static String toPersianDigits"
        if anchor in cfg:
            cfg = cfg.replace(anchor, helper + anchor, 1)
        else:
            print("WARN: toPersianDigits anchor not found (a11yIsPersianUi helper not inserted)")
            cfg = cfg.replace("a11yIsPersianUi()", '"fa".equalsIgnoreCase(java.util.Locale.getDefault().getLanguage())')
    # a11y-fork: default values of Accessible Settings, chosen by the user. They apply on a
    # fresh install (a value the user already saved always wins):
    #   progress step 1 %, status in preview ON, forward-to-saved-without-quote OFF,
    #   recording start beep OFF, solar calendar OFF, links menu OFF.
    for pref, val in (("PREF_SOLAR_CALENDAR", "false"), ("PREF_SHOW_STATUS_IN_PREVIEW", "true"),
                      ("PREF_FORWARD_SAVED_NO_QUOTE", "false"), ("PREF_RECORDING_BEEP", "false"),
                      ("PREF_LINKS_MENU", "false")):
        cfg = re.sub(r"getBoolean\(" + pref + r",\s*(?:true|false)\)", "getBoolean(" + pref + ", " + val + ")", cfg)
    m_step = re.search(r"public static int getProgressStep\(\) \{.*?\n    \}\n", cfg, re.S)
    if m_step:
        fixed = m_step.group(0).replace("PREF_PROGRESS_STEP, 5)", "PREF_PROGRESS_STEP, 1)").replace("step = 5;", "step = 1;").replace("return 5;", "return 1;")
        cfg = cfg[:m_step.start()] + fixed + cfg[m_step.end():]
    else:
        print("WARN: getProgressStep not found (default 1 percent)")
    dst.write_text(cfg, encoding="utf-8")
    print("A11yConfig.java installed + Solar date fixed/date-only + small-file setting added")


def _inject_progress_announce(java_path: Path) -> None:
    if not java_path.exists():
        print(f"WARN: {java_path.name} missing")
        return
    t = java_path.read_text(encoding="utf-8")
    # Cached Telegram trees can already contain an older accessibility patch.
    # Normalize that stale block instead of returning early, otherwise an old
    # unqualified LocaleController/R reference can survive into the build.
    stale_patterns = [
        'LocaleController.formatString("A11yPercent", R.string.A11yPercent, step)',
        'parent.announceForAccessibility(step + " percent");',
    ]
    fixed_call = 'org.telegram.messenger.LocaleController.formatString("A11yPercent", org.telegram.messenger.R.string.A11yPercent, step)'
    changed_stale = False
    for stale in stale_patterns:
        if stale in t:
            if stale.startswith('parent.announceForAccessibility'):
                t = t.replace(stale, 'parent.announceForAccessibility(' + fixed_call + ');')
            else:
                t = t.replace(stale, fixed_call)
            changed_stale = True
    if changed_stale:
        java_path.write_text(t, encoding="utf-8")
        print(f"{java_path.name} stale progress references normalized")
    if "a11y-fork: announce progress only if focused" in t:
        print(f"{java_path.name} already patched (focus-aware)")
        return
    if "a11y-fork: announce progress" in t:
        t = re.sub(
            r"\n\s*// a11y-fork: announce progress[\s\S]*?if \(pct == 0\) a11yLastAnnouncedPercent = -1;\s*\}\s*\} catch \(Throwable ignore\) \{\}\s*\}\s*",
            "\n",
            t,
            count=1,
        )
    if "a11yLastAnnouncedPercent" not in t:
        if "private View parent;" in t:
            t = t.replace(
                "private View parent;",
                "private View parent;\n    // a11y-fork: announce progress\n    private int a11yLastAnnouncedPercent = -1;",
                1,
            )
        elif "private float currentProgress = 0;" in t:
            t = t.replace(
                "private float currentProgress = 0;",
                "private float currentProgress = 0;\n    // a11y-fork: announce progress\n    private int a11yLastAnnouncedPercent = -1;",
                1,
            )
    inject = """
        // a11y-fork: announce progress only if focused on this message cell
        if (parent != null) {
            try {
                Object amObj = parent.getContext().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);
                android.view.accessibility.AccessibilityManager am = (android.view.accessibility.AccessibilityManager) amObj;
                if (am != null && am.isEnabled()) {
                    boolean focused = parent.isAccessibilityFocused();
                    if (!focused) {
                        android.view.View v = parent;
                        while (v != null && !focused) {
                            if (v.isAccessibilityFocused()) {
                                focused = true;
                                break;
                            }
                            android.view.ViewParent vp = v.getParent();
                            v = (vp instanceof android.view.View) ? (android.view.View) vp : null;
                        }
                    }
                    if (focused) {
                        int pct = Math.round(value * 100f);
                        if (pct >= 100) pct = 100;
                        if (pct < 0) pct = 0;
                        int stepSize = 5;
                        try { stepSize = org.telegram.messenger.A11yConfig.getProgressStep(); } catch (Throwable ignore2) {}
                        if (stepSize <= 0) stepSize = 5;
                        int step = (pct / stepSize) * stepSize;
                        if (pct >= 100) {
                            if (a11yLastAnnouncedPercent != 100) {
                                a11yLastAnnouncedPercent = 100;
                                parent.announceForAccessibility(org.telegram.messenger.LocaleController.getString(
                                        org.telegram.messenger.R.string.A11yDownloaded));
                            }
                        } else if (step != a11yLastAnnouncedPercent) {
                            a11yLastAnnouncedPercent = step;
                            parent.announceForAccessibility(org.telegram.messenger.LocaleController.formatString(
                                    "A11yPercent", org.telegram.messenger.R.string.A11yPercent, step));
                        }
                        if (pct == 0) a11yLastAnnouncedPercent = -1;
                    }
                }
            } catch (Throwable ignore) {}
        }
"""
    m = re.search(r"public void setProgress\(float value, boolean animated\) \{\n", t)
    if not m:
        print(f"WARN: setProgress not found in {java_path.name}")
        return
    t = t[: m.end()] + inject + t[m.end() :]
    java_path.write_text(t, encoding="utf-8")
    print(f"{java_path.name} progress announce (focus-only) OK")


def patch_radial_progress() -> None:
    _inject_progress_announce(JAVA / "org/telegram/ui/Components/RadialProgress2.java")
    _inject_progress_announce(JAVA / "org/telegram/ui/Components/RadialProgress.java")


def patch_dialogcell_name_then_type() -> None:
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    if not dc.exists():
        print("WARN: DialogCell missing")
        return
    t = dc.read_text(encoding="utf-8")
    if "a11y-fork: name then type" in t:
        print("DialogCell already patched")
        return
    old_chat = """            } else if (chat != null) {
                if (chat.broadcast) {
                    sb.append(getString(R.string.AccDescrChannel));
                } else {
                    sb.append(getString(R.string.AccDescrGroup));
                }
                sb.append(". ");
                sb.append(chat.title);
                sb.append(". ");
            }"""
    new_chat = """            } else if (chat != null) {
                // a11y-fork: name then type
                sb.append(chat.title);
                sb.append(". ");
                if (chat.broadcast) {
                    sb.append(getString(R.string.AccDescrChannel));
                } else {
                    sb.append(getString(R.string.AccDescrGroup));
                }
                sb.append(". ");
            }"""
    old_bot = """                    if (user.bot) {
                        sb.append(getString(R.string.Bot));
                        sb.append(". ");
                    }
                    if (user.self) {
                        sb.append(getString(R.string.SavedMessages));
                    } else {
                        sb.append(ContactsController.formatName(user.first_name, user.last_name));
                    }"""
    new_bot = """                    // a11y-fork: name then type for bots
                    if (user.self) {
                        sb.append(getString(R.string.SavedMessages));
                    } else {
                        sb.append(ContactsController.formatName(user.first_name, user.last_name));
                        if (user.bot) {
                            sb.append(". ");
                            sb.append(getString(R.string.Bot));
                        }
                    }"""
    changed = False
    if old_chat in t:
        t = t.replace(old_chat, new_chat, 1)
        changed = True
        print("DialogCell chat name-then-type OK")
    else:
        print("WARN: DialogCell chat block not found")
    if old_bot in t:
        t = t.replace(old_bot, new_bot, 1)
        changed = True
        print("DialogCell bot name-then-type OK")
    else:
        print("WARN: DialogCell bot block not found")
    if changed:
        dc.write_text(t, encoding="utf-8")


def patch_hide_share_and_comment() -> None:
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        print("WARN: ChatMessageCell missing")
        return
    t = cmc.read_text(encoding="utf-8")
    if "a11y-fork: hide share" not in t:
        t2, n = re.subn(
            r"(boolean\s+checkNeedDrawShareButton\s*\([^)]*\)\s*\{)",
            r"\1\n        // a11y-fork: hide share button between messages\n        if (true) return false;",
            t,
            count=1,
        )
        if n:
            t = t2
            print("Hide share OK")
    if "a11y-fork: hide comment button" not in t and "drawCommentButton = true;" in t:
        t = t.replace(
            "drawCommentButton = true;",
            "drawCommentButton = false; // a11y-fork: hide comment button between messages",
        )
        print("Hide leave-comment OK")
    cmc.write_text(t, encoding="utf-8")


def patch_forward_handler(t: str) -> str:
    # If the broken old handler exists, remove it completely. It is the source
    # of the observed NO_QUOTE -> Saved Messages fall-through.
    if "a11y-fork: OPTION_FORWARD_NO_QUOTE" in t:
        start = t.find("            case OPTION_FORWARD_NO_QUOTE: // a11y-fork: OPTION_FORWARD_NO_QUOTE")
        end = t.find("            case OPTION_FORWARD: {", start)
        if start >= 0 and end >= 0:
            t = t[:start] + t[end:]

    # Ensure the no-quote case shares the normal Forward handler, not Saved.
    normal = "            case OPTION_FORWARD: {"
    shared = "            case OPTION_FORWARD_NO_QUOTE: // a11y-fork: forward without quote\n                IS_FORWARD_NO_QUOTE = true;\n                // fall through to the normal Forward UI\n            case OPTION_FORWARD: {"
    if "case OPTION_FORWARD_NO_QUOTE: // a11y-fork: forward without quote" not in t:
        if normal not in t:
            raise RuntimeError("normal OPTION_FORWARD case not found")
        t = t.replace(normal, shared, 1)

    # Add/replace Saved Messages handler immediately before normal Forward.
    marker = "            case OPTION_FORWARD_NO_QUOTE: // a11y-fork: forward without quote\n"
    saved_start = t.find(marker)
    if saved_start < 0:
        raise RuntimeError("forward no-quote case insertion failed")
    # Insert Saved case before no-quote case if it is not already present.
    if "a11y-fork: forward to Saved Messages" not in t:
        saved = '''            case OPTION_FORWARD_TO_SAVED: { // a11y-fork: forward to Saved Messages\n                if (selectedObject != null) {\n                    try {\n                        java.util.ArrayList<MessageObject> toSend = new java.util.ArrayList<>();\n                        if (selectedObjectGroup != null && selectedObjectGroup.messages != null) {\n                            toSend.addAll(selectedObjectGroup.messages);\n                        } else {\n                            toSend.add(selectedObject);\n                        }\n                        IS_FORWARD_NO_QUOTE = org.telegram.messenger.A11yConfig.getForwardSavedNoQuote();\n                        long savedId = getUserConfig().getClientUserId();\n                        getSendMessagesHelper().sendMessage(toSend, savedId, false, false, true, 0, 0);\n                        try {\n                            if (getParentActivity() != null) {\n                                getParentActivity().getWindow().getDecorView().announceForAccessibility(\"Forwarded to Saved Messages\");\n                            }\n                        } catch (Throwable ignore) {}\n                    } catch (Throwable e) {\n                        FileLog.e(e);\n                    }\n                }\n                selectedObject = null;\n                selectedObjectToEditCaption = null;\n                selectedObjectGroup = null;\n                break;\n            }\n'''
        t = t[:saved_start] + saved + t[saved_start:]
    if "a11y-fork: forward here handler" not in t:
        here = (
            "            case OPTION_FORWARD_HERE: { // a11y-fork: forward here handler\n"
            "                if (selectedObject != null) {\n"
            "                    try {\n"
            "                        java.util.ArrayList<MessageObject> toSend = new java.util.ArrayList<>();\n"
            "                        if (selectedObjectGroup != null && selectedObjectGroup.messages != null) {\n"
            "                            toSend.addAll(selectedObjectGroup.messages);\n"
            "                        } else {\n"
            "                            toSend.add(selectedObject);\n"
            "                        }\n"
            "                        IS_FORWARD_NO_QUOTE = false;\n"
            "                        getSendMessagesHelper().sendMessage(toSend, dialog_id, false, false, true, 0, getThreadMessage(), 0, 0);\n"
            "                        try {\n"
            "                            if (getParentActivity() != null) {\n"
            "                                getParentActivity().getWindow().getDecorView().announceForAccessibility(LocaleController.getString(R.string.A11yForwardedHere));\n"
            "                            }\n"
            "                        } catch (Throwable ignore) {}\n"
            "                    } catch (Throwable e) {\n"
            "                        FileLog.e(e);\n"
            "                    }\n"
            "                }\n"
            "                selectedObject = null;\n"
            "                selectedObjectToEditCaption = null;\n"
            "                selectedObjectGroup = null;\n"
            "                break;\n"
            "            }\n"
        )
        idx = t.find(marker)
        if idx < 0:
            raise RuntimeError("forward here handler anchor not found")
        t = t[:idx] + here + t[idx:]
    return t


def patch_forward_menu_extras() -> None:
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    smh = JAVA / "org/telegram/messenger/SendMessagesHelper.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (forward menu)")
        return
    if smh.exists():
        t = smh.read_text(encoding="utf-8")
        if "a11y-fork: drop-author one-shot v2" not in t:
            old = "req.drop_author = forwardFromMyName;"
            new = "req.drop_author = forwardFromMyName || org.telegram.ui.ChatActivity.IS_FORWARD_NO_QUOTE; org.telegram.ui.ChatActivity.IS_FORWARD_NO_QUOTE = false;"
            if old in t:
                t=t.replace(old,new,1); smh.write_text(t,encoding="utf-8"); print("drop_author one-shot v2 OK")
    t=ca.read_text(encoding="utf-8")
    # IMPORTANT: the forward handler itself also contains the token
    # IS_FORWARD_NO_QUOTE, so checking `if "IS_FORWARD_NO_QUOTE" not in t`
    # is not sufficient to detect the field declaration.
    if "public static boolean IS_FORWARD_NO_QUOTE" not in t:
        anchor="protected TLRPC.Chat currentChat;"
        if anchor in t:
            t=t.replace(anchor,"public static boolean IS_FORWARD_NO_QUOTE = false;\n    "+anchor,1)
            print("IS_FORWARD_NO_QUOTE field OK")
        else:
            print("WARN: currentChat anchor not found (IS_FORWARD_NO_QUOTE field)")

    # The new switch cases use these accessibility option IDs.  They must be
    # declared inside ChatActivity; Python constants at the top of this
    # script do not exist in the generated Java source.
    option_decl = (
        "private static final int OPTION_FORWARD_NO_QUOTE = 200;\n"
        "    private static final int OPTION_FORWARD_TO_SAVED = 202;\n"
        "    private static final int OPTION_FORWARD_HERE = %d;" % OPTION_FORWARD_HERE
    )
    if "private static final int OPTION_FORWARD_NO_QUOTE = 200;" not in t:
        field_anchor = "public static boolean IS_FORWARD_NO_QUOTE = false;"
        if field_anchor in t:
            t=t.replace(field_anchor, field_anchor+"\n    "+option_decl, 1)
            print("Forward option constants OK")
        else:
            print("WARN: IS_FORWARD_NO_QUOTE field anchor not found (option constants)")
    if "a11y-fork: forward menu extras" not in t:
        old=("                if (canForward) {\n"
             "                    items.add(LocaleController.getString(R.string.Forward));\n"
             "                    options.add(OPTION_FORWARD);\n"
             "                    icons.add(R.drawable.msg_forward);\n"
             "                }")
        new=("                if (canForward) {\n"
             "                    items.add(LocaleController.getString(R.string.Forward));\n"
             "                    options.add(OPTION_FORWARD);\n"
             "                    icons.add(R.drawable.msg_forward);\n"
             "                    // a11y-fork: forward menu extras\n"
             "                    items.add(LocaleController.getString(R.string.A11yForwardWithoutQuote));\n"
             f"                    options.add({OPTION_FORWARD_NO_QUOTE});\n"
             "                    icons.add(R.drawable.msg_forward);\n"
             "                    if (org.telegram.messenger.A11yConfig.getForwardHere()) { // a11y-fork: forward here (setting, default OFF)\n"
             "                        items.add(LocaleController.getString(R.string.A11yForwardHere));\n"
             f"                        options.add({OPTION_FORWARD_HERE});\n"
             "                        icons.add(R.drawable.msg_forward);\n"
             "                    }\n"
             "                    items.add(LocaleController.getString(R.string.A11yForwardToSaved));\n"
             f"                    options.add({OPTION_FORWARD_TO_SAVED});\n"
             "                    icons.add(R.drawable.msg_forward);\n"
             "                }")
        if old in t: t=t.replace(old,new,1); print("Forward menu extras OK")
        else: print("WARN: canForward menu block not found")
    t=patch_forward_handler(t)
    ca.write_text(t,encoding="utf-8")
    print("Forward option handlers v2 OK")


def patch_photo_longpress_message_options() -> None:
    """Force TalkBack long-press on photo-only/no-caption messages into Message Options."""
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (photo long-press)")
        return
    t = ca.read_text(encoding="utf-8")
    marker = "a11y-fork: photo-no-caption longpress v1"
    if marker in t:
        return
    needle = """            if (view instanceof ChatMessageCell && (((ChatMessageCell) view).getMessageObject() != null && ((ChatMessageCell) view).getMessageObject().type != MessageObject.TYPE_JOINED_CHANNEL)) {
"""
    if needle not in t:
        print("WARN: ChatActivity message long-press anchor not found (photo case)")
        return
    insert = """            // a11y-fork: photo-no-caption longpress v1
            if (view instanceof ChatMessageCell && !actionBar.isActionModeShowed()) {
                try {
                    MessageObject a11yPhotoMessage = ((ChatMessageCell) view).getMessageObject();
                    boolean a11yPhotoOnly = a11yPhotoMessage != null
                            && MessageObject.isPhoto(a11yPhotoMessage.messageOwner)
                            && android.text.TextUtils.isEmpty(a11yPhotoMessage.messageOwner.message);
                    android.view.accessibility.AccessibilityManager a11yPhotoAm =
                            (android.view.accessibility.AccessibilityManager) getParentActivity()
                                    .getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);
                    if (a11yPhotoOnly && a11yPhotoAm != null && a11yPhotoAm.isEnabled()) {
                        result = createMenu(view, true, false, x, y, true);
                        return true;
                    }
                } catch (Throwable ignore) {
                }
            }

"""
    t=t.replace(needle,insert+needle,1)
    ca.write_text(t,encoding="utf-8")
    print("Photo-only/no-caption TalkBack long-press -> Message Options OK")

def patch_reactions_as_menu() -> None:
    """
    Accessibility-fork: put the emoji reactions row behind a "Reactions"
    menu item (hidden/collapsed by default, revealed on tap) instead of it
    always being a focusable row above the message menu -- keeps TalkBack
    navigation from being cluttered by a rarely-used control. Inserted at
    the SAME anchor Bot Buttons/Select use, and this function is called
    before those two in main(), so the final order is:
    Reactions, Bot Buttons, Select (last).
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (reactions menu)")
        return
    t = ca.read_text(encoding="utf-8")
    # The workflow already applies patches/04-comment-and-reactions.patch,
    # which implements the Reactions menu item using OPTION_TOGGLE_REACTIONS_ROW.
    # Do not add a second item with OPTION_REACTIONS_MENU.
    if "OPTION_TOGGLE_REACTIONS_ROW" in t and "Accessibility: put reactions behind" in t:
        print("ChatActivity Reactions menu already provided by 04-comment-and-reactions.patch")
        return
    if "a11y-fork: reactions menu item" in t:
        print("ChatActivity reactions-menu already patched")
        return

    # patch_reactions_as_menu injects into fillMessageMenu(), where the
    # createMenu() local variable named isReactionsAvailableFinal does not
    # exist.  Define an equivalent local value here, based on Telegram's
    # current MessageObject API, before the menu item is inserted.
    if "a11y-fork: reactions availability for menu" not in t:
        reactions_availability_anchor = (
            "        final MessageObject.GroupedMessages groupedMessages = selectedObjectGroup;\n"
            "        final int type = getMessageType(message);\n"
        )
        reactions_availability_insert = (
            "        final MessageObject.GroupedMessages groupedMessages = selectedObjectGroup;\n"
            "        final int type = getMessageType(message);\n"
            "        // a11y-fork: reactions availability for menu\n"
            "        final boolean isReactionsAvailableFinal = message != null && message.isReactionsAvailable();\n"
        )
        if reactions_availability_anchor in t:
            t = t.replace(reactions_availability_anchor, reactions_availability_insert, 1)
            print("ChatActivity reactions availability declaration OK")
        else:
            print("WARN: fillMessageMenu anchor not found (reactions availability)")

    old_item = (
        "        if (message.isSponsored() && !getUserConfig().isPremium() "
        "&& !getMessagesController().premiumFeaturesBlocked() && !message.sponsoredCanReport) {\n"
    )
    new_item = (
        "        // a11y-fork: reactions menu item\n"
        "        accessibilityReactionsToggleIndex = -1;\n"
        "        if (isReactionsAvailableFinal) {\n"
        "            items.add(LocaleController.getString(R.string.Reactions));\n"
        "            icons.add(R.drawable.msg_reactions2);\n"
        f"            options.add({OPTION_REACTIONS_MENU});\n"
        "            accessibilityReactionsToggleIndex = items.size() - 1;\n"
        "        }\n"
        "\n"
        "        if (message.isSponsored() && !getUserConfig().isPremium() "
        "&& !getMessagesController().premiumFeaturesBlocked() && !message.sponsoredCanReport) {\n"
    )
    if old_item not in t:
        print("WARN: ChatActivity sponsored-item anchor not found (reactions menu item)")
        return
    t = t.replace(old_item, new_item, 1)

    if "accessibilityReactionsToggleIndex" not in t.split("a11y-fork: reactions menu item")[0]:
        # add the field declaration once, right before the class body's first field-like anchor
        field_anchor = "public class ChatActivity"
        idx = t.find(field_anchor)
        if idx != -1:
            brace_idx = t.find("{", idx)
            if brace_idx != -1:
                t = (
                    t[: brace_idx + 1]
                    + "\n    private int accessibilityReactionsToggleIndex = -1; // a11y-fork: reactions menu item\n"
                    + t[brace_idx + 1 :]
                )

    old_toggle = (
        "                    scrimPopupContainerLayout.addView(reactionsLayout, params);\n"
        "                    scrimPopupContainerLayout.setReactionsLayout(reactionsLayout);\n"
    )
    new_toggle = (
        "                    scrimPopupContainerLayout.addView(reactionsLayout, params);\n"
        "                    scrimPopupContainerLayout.setReactionsLayout(reactionsLayout);\n"
        "\n"
        "                    // a11y-fork: reactions menu item -- hide the reactions row\n"
        "                    // by default; the \"Reactions\" menu item reveals it on tap.\n"
        "                    reactionsLayout.setVisibility(View.GONE);\n"
        "                    if (accessibilityReactionsToggleIndex >= 0 && scrimPopupWindowItems != null\n"
        "                        && accessibilityReactionsToggleIndex < scrimPopupWindowItems.length\n"
        "                        && scrimPopupWindowItems[accessibilityReactionsToggleIndex] != null) {\n"
        "                        final ReactionsContainerLayout reactionsLayoutForToggle = reactionsLayout;\n"
        "                        scrimPopupWindowItems[accessibilityReactionsToggleIndex].setOnClickListener(reactionsToggleView -> {\n"
        "                            boolean show = reactionsLayoutForToggle.getVisibility() != View.VISIBLE;\n"
        "                            reactionsLayoutForToggle.setVisibility(show ? View.VISIBLE : View.GONE);\n"
        "                        });\n"
        "                    }\n"
    )
    if old_toggle not in t:
        print("WARN: ChatActivity reactionsLayout anchor not found (visibility toggle)")
    else:
        t = t.replace(old_toggle, new_toggle, 1)

    ca.write_text(t, encoding="utf-8")
    print("ChatActivity reactions-menu item+toggle OK")


def patch_longpress_message_menu() -> None:
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing")
        return
    t = ca.read_text(encoding="utf-8")

    # Prefer single-message menu under TalkBack (avoids multi-select path inside createMenu)
    if "a11y-fork: createMenu single under a11y" not in t:
        old_cm = (
            "            if (!actionBar.isActionModeShowed() && (!isReport() || showMenu)) {\n"
            "                result = createMenu(view, false, true, x, y, true);\n"
            "            } else {"
        )
        new_cm = (
            "            if (!actionBar.isActionModeShowed() && (!isReport() || showMenu)) {\n"
            "                // a11y-fork: createMenu single under a11y\n"
            "                boolean a11yMenu = false;\n"
            "                try {\n"
            "                    android.view.accessibility.AccessibilityManager amM = (android.view.accessibility.AccessibilityManager) getParentActivity().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);\n"
            "                    a11yMenu = amM != null && amM.isEnabled();\n"
            "                } catch (Throwable ignore) {}\n"
            "                if (a11yMenu) {\n"
            "                    result = createMenu(view, true, false, x, y, true);\n"
            "                } else {\n"
            "                    result = createMenu(view, false, true, x, y, true);\n"
            "                }\n"
            "            } else {"
        )
        if old_cm in t:
            t = t.replace(old_cm, new_cm, 1)
            print("createMenu single under a11y OK")
        else:
            print("WARN: createMenu long-click block not found")

    old_ms = (
        "            if (view instanceof ChatMessageCell && (((ChatMessageCell) view).getMessageObject() != null && ((ChatMessageCell) view).getMessageObject().type != MessageObject.TYPE_JOINED_CHANNEL)) {\n"
        "                startMultiselect(position);\n"
        "                result = true;\n"
        "            }"
    )
    new_ms = (
        "            if (view instanceof ChatMessageCell && (((ChatMessageCell) view).getMessageObject() != null && ((ChatMessageCell) view).getMessageObject().type != MessageObject.TYPE_JOINED_CHANNEL)) {\n"
        "                // a11y-fork: with TalkBack, long-press only opens menu\n"
        "                boolean a11yOn = false;\n"
        "                try {\n"
        "                    android.view.accessibility.AccessibilityManager am = (android.view.accessibility.AccessibilityManager) getParentActivity().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);\n"
        "                    a11yOn = am != null && am.isEnabled();\n"
        "                } catch (Throwable ignore) {}\n"
        "                if (!a11yOn || actionBar.isActionModeShowed()) {\n"
        "                    startMultiselect(position);\n"
        "                }\n"
        "                result = true;\n"
        "            }"
    )
    if "a11y-fork: with TalkBack, long-press only opens menu" not in t:
        if old_ms in t:
            t = t.replace(old_ms, new_ms, 1)
            print("Long-press skip startMultiselect OK")
        else:
            print("WARN: startMultiselect block not found")

    old_dlp = (
        "            createMenu(cell, false, false, x, y, false);\n"
        "            startMultiselect(chatListView.getChildAdapterPosition(cell));"
    )
    new_dlp = (
        "            // a11y-fork: under TalkBack, long-press must open the full\n"
        "            // single-message Message Options menu for every ChatMessageCell\n"
        "            // type (text, photo, video, document/file, voice, etc.).\n"
        "            boolean a11yOn2 = false;\n"
        "            try {\n"
        "                android.view.accessibility.AccessibilityManager am2 = (android.view.accessibility.AccessibilityManager) getParentActivity().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);\n"
        "                a11yOn2 = am2 != null && am2.isEnabled();\n"
        "            } catch (Throwable ignore) {}\n"
        "            if (a11yOn2) {\n"
        "                createMenu(cell, true, false, x, y, true);\n"
        "            } else {\n"
        "                createMenu(cell, false, false, x, y, false);\n"
        "                startMultiselect(chatListView.getChildAdapterPosition(cell));\n"
        "            }"
    )
    if "a11y-fork: under TalkBack, long-press must open the full" not in t:
        if old_dlp in t:
            t = t.replace(old_dlp, new_dlp, 1)
            print("didLongPress universal TalkBack Message Options OK")
        elif "a11y-fork: do not auto-start multi-select under TalkBack" in t:
            old_v1 = (
                "            createMenu(cell, false, false, x, y, false);\n"
                "            // a11y-fork: do not auto-start multi-select under TalkBack\n"
                "            boolean a11yOn2 = false;\n"
                "            try {\n"
                "                android.view.accessibility.AccessibilityManager am2 = (android.view.accessibility.AccessibilityManager) getParentActivity().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);\n"
                "                a11yOn2 = am2 != null && am2.isEnabled();\n"
                "            } catch (Throwable ignore) {}\n"
                "            if (!a11yOn2 || actionBar.isActionModeShowed()) {\n"
                "                startMultiselect(chatListView.getChildAdapterPosition(cell));\n"
                "            }"
            )
            if old_v1 in t:
                t = t.replace(old_v1, new_dlp, 1)
                print("didLongPress universal TalkBack Message Options upgraded OK")
            else:
                print("WARN: didLongPress v1 block not found")
        else:
            print("WARN: didLongPress block not found")

    # Telegram 12.10.5 uses a direct ChatMessageCellDelegate.didLongPress implementation
    # for accessibility-triggered long clicks. The older anchor above may not exist, so
    # patch the exact current delegate method as a safe fallback.
    if "a11y-fork: 12.10.5 TalkBack didLongPress" not in t and "a11y-fork: under TalkBack, long-press must open the full" not in t:
        old_dlp_125 = '        public void didLongPress(ChatMessageCell cell, float x, float y) {\n            createMenu(cell, false, false, x, y, false);\n            startMultiselect(chatListView.getChildAdapterPosition(cell));\n        }'
        new_dlp_125 = '        public void didLongPress(ChatMessageCell cell, float x, float y) {\n            // a11y-fork: 12.10.5 TalkBack didLongPress\n            boolean a11yTalkBack = false;\n            try {\n                android.view.accessibility.AccessibilityManager am = (android.view.accessibility.AccessibilityManager) getParentActivity().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);\n                a11yTalkBack = am != null && am.isEnabled() && am.isTouchExplorationEnabled();\n            } catch (Throwable ignore) {}\n            if (a11yTalkBack) {\n                createMenu(cell, true, false, x, y, true);\n            } else {\n                createMenu(cell, false, false, x, y, false);\n                startMultiselect(chatListView.getChildAdapterPosition(cell));\n            }\n        }'
        if old_dlp_125 in t:
            t=t.replace(old_dlp_125,new_dlp_125,1)
            print("12.10.5 TalkBack didLongPress routing OK")
        else:
            print("WARN: 12.10.5 didLongPress exact anchor not found")

    if "a11y-fork: OPTION_SELECT_MESSAGE menu" not in t:
        needle = "        if (message.isSponsored() && !getUserConfig().isPremium()"
        insert = (
            f"        // a11y-fork: OPTION_SELECT_MESSAGE menu\n"
            f"        if (!actionBar.isActionModeShowed() && message != null && message.contentType == 0 && !message.isSponsored()) {{\n"
            f"            items.add(LocaleController.getString(R.string.Select));\n"
            f"            options.add({OPTION_SELECT_MESSAGE});\n"
            f"            icons.add(R.drawable.msg_forward);\n"
            f"        }}\n\n"
            f"        if (message.isSponsored() && !getUserConfig().isPremium()"
        )
        if needle in t:
            t = t.replace(needle, insert, 1)
            print("Select menu item OK")
        else:
            print("WARN: fillMessageMenu inject point not found")

    if "a11y-fork: OPTION_SELECT_MESSAGE handler" not in t:
        old_case = "            case OPTION_RETRY: {"
        new_case = (
            f"            case {OPTION_SELECT_MESSAGE}: {{ // a11y-fork: OPTION_SELECT_MESSAGE handler\n"
            f"                if (selectedObject != null) {{\n"
            f"                    try {{\n"
            f"                        MessageObject toSelect = selectedObject;\n"
            f"                        closeMenu();\n"
            f"                        createActionMode();\n"
            f"                        if (actionBar != null) {{\n"
            f"                            actionBar.showActionMode(true, null, null, null, null, null, 0);\n"
            f"                        }}\n"
            f"                        addToSelectedMessages(toSelect, false);\n"
            f"                        updateActionModeTitle();\n"
            f"                        updateVisibleRows();\n"
            f"                        if (chatActivityEnterView != null) chatActivityEnterView.preventInput = true;\n"
            f"                        if (selectedMessagesCountTextView != null) {{\n"
            f"                            selectedMessagesCountTextView.setText(LocaleController.formatPluralString(\"MessagesSelected\", selectedMessagesIds[0].size() + selectedMessagesIds[1].size()), false);\n"
            f"                        }}\n"
            f"                        try {{\n"
            f"                            if (getParentActivity() != null) {{\n"
            f"                                getParentActivity().getWindow().getDecorView().announceForAccessibility(\"Selected\");\n"
            f"                            }}\n"
            f"                        }} catch (Throwable ignore) {{}}\n"
            f"                    }} catch (Throwable e) {{\n"
            f"                        FileLog.e(e);\n"
            f"                    }}\n"
            f"                }}\n"
            f"                selectedObject = null;\n"
            f"                selectedObjectToEditCaption = null;\n"
            f"                selectedObjectGroup = null;\n"
            f"                break;\n"
            f"            }}\n"
            f"            case OPTION_RETRY: {{"
        )
        if old_case in t:
            t = t.replace(old_case, new_case, 1)
            print("Select handler OK")
        else:
            print("WARN: OPTION_RETRY case not found")
    ca.write_text(t, encoding="utf-8")



def patch_auto_download_policy() -> None:
    """Default automatic downloads OFF for photo/video/document on all networks;
    voice messages remain enabled. User changes are not overridden after first run.
    """
    dc = JAVA / "org/telegram/messenger/DownloadController.java"
    if not dc.exists():
        print("WARN: DownloadController missing (auto-download policy)")
        return
    t = dc.read_text(encoding="utf-8")
    marker = "a11y-fork: default auto-download policy v2"
    if marker not in t:
        anchor = "    public DownloadController(int instance) {"
        helper = (
            "    // " + marker + "\n"
            "    private void applyA11yDefaultAutoDownloadPolicy() {\n"
            "        try {\n"
            "            android.content.SharedPreferences prefs = MessagesController.getMainSettings(currentAccount);\n"
            "            if (prefs.getBoolean(\"a11y_auto_download_defaults_applied_v2\", false)) return;\n"
            "            int voiceOnlyMask = 0;\n"
            "            for (int i = 0; i < 4; i++) {\n"
            "                mobilePreset.mask[i] = voiceOnlyMask; wifiPreset.mask[i] = voiceOnlyMask; roamingPreset.mask[i] = voiceOnlyMask;\n"
            "            }\n"
            "            // enabled MUST stay true: Telegram checks preset.enabled BEFORE anything else, so with\n"
            "            // enabled=false even voice messages (which bypass the mask) never auto-download and the\n"
            "            // small-files radio setting could not do anything. The mask (0) already keeps photo /\n"
            "            // video / document from auto-downloading.\n"
            "            mobilePreset.enabled = true; wifiPreset.enabled = true; roamingPreset.enabled = true;\n"
            "            mobilePreset.preloadVideo = false; wifiPreset.preloadVideo = false; roamingPreset.preloadVideo = false;\n"
            "            mobilePreset.preloadMusic = false; wifiPreset.preloadMusic = false; roamingPreset.preloadMusic = false;\n"
            "            currentMobilePreset = 3; currentWifiPreset = 3; currentRoamingPreset = 3;\n"
            "            prefs.edit().putString(\"mobilePreset\", mobilePreset.toString()).putString(\"wifiPreset\", wifiPreset.toString()).putString(\"roamingPreset\", roamingPreset.toString())\n"
            "                    .putInt(\"currentMobilePreset\", 3).putInt(\"currentWifiPreset\", 3).putInt(\"currentRoamingPreset\", 3)\n"
            "                    .putBoolean(\"a11y_auto_download_defaults_applied_v2\", true).commit();\n"
            "            checkAutodownloadSettings();\n"
            "        } catch (Throwable e) { FileLog.e(e); }\n"
            "    }\n\n"
        )
        if anchor in t:
            t=t.replace(anchor,helper+anchor,1)
        else:
            print("WARN: DownloadController constructor anchor not found")
            return
        anchor2 = """        if (getUserConfig().isClientActivated()) {
            checkAutodownloadSettings();
        }
"""
        repl2 = """        // a11y-fork: default auto-download policy v2
        applyA11yDefaultAutoDownloadPolicy();
        if (getUserConfig().isClientActivated()) {
            checkAutodownloadSettings();
        }
"""
        if anchor2 in t: t=t.replace(anchor2,repl2,1)
        else: print("WARN: DownloadController post-constructor anchor not found")
    dc.write_text(t,encoding="utf-8")
    print("DownloadController first-run auto-download defaults OK")

def patch_voice_bitrate() -> None:
    audio = ROOT / "jni/audio.c"
    if audio.exists():
        t = audio.read_text(encoding="utf-8", errors="replace")
        if "a11y_record_bitrate" not in t:
            t = t.replace(
                "const opus_int32 bitrate = OPUS_BITRATE_MAX;",
                "/* a11y-fork */ opus_int32 a11y_record_bitrate = 32000;\nconst opus_int32 bitrate = OPUS_BITRATE_MAX;",
                1,
            )
            t = t.replace(
                "result = opus_encoder_ctl(_encoder, OPUS_SET_BITRATE(bitrate));",
                "result = opus_encoder_ctl(_encoder, OPUS_SET_BITRATE(a11y_record_bitrate > 0 ? a11y_record_bitrate : bitrate));",
                1,
            )
            start_line = "JNIEXPORT jint Java_org_telegram_messenger_MediaController_startRecord"
            if start_line in t and "setRecordBitrate" not in t:
                jni = (
                    "JNIEXPORT void Java_org_telegram_messenger_MediaController_setRecordBitrate"
                    "(JNIEnv *env, jclass clazz, jint br) {\n"
                    "    if (br > 0) a11y_record_bitrate = br;\n"
                    "}\n\n" + start_line
                )
                t = t.replace(start_line, jni, 1)
            audio.write_text(t, encoding="utf-8")
            print("audio.c bitrate OK")
        else:
            print("audio.c already patched")
    mc = JAVA / "org/telegram/messenger/MediaController.java"
    if not mc.exists():
        return
    t = mc.read_text(encoding="utf-8")
    if "setRecordBitrate" not in t:
        t = t.replace(
            "private native int startRecord(String path, int sampleRate);",
            "private native int startRecord(String path, int sampleRate);\n    // a11y-fork\n    public native void setRecordBitrate(int bitrate);",
            1,
        )
        print("MediaController native setRecordBitrate OK")
    if "A11yConfig.applyVoiceBitrateToNative" not in t:
        t2, n = re.subn(
            r"(if \(startRecord\(recordingAudioFile\.getPath\(\), sampleRate\) == 0\))",
            r"try { org.telegram.messenger.A11yConfig.applyVoiceBitrateToNative(); } catch (Throwable ignore) {}\n                    \1",
            t,
        )
        if n:
            t = t2
            print(f"MediaController apply voice before record x{n}")
    mc.write_text(t, encoding="utf-8")


def patch_chat_message_cell_float_coordinates() -> None:
    """
    Fix the TalkBack long-press accessibility injection on current Telegram:
    lastTouchX/lastTouchY are floats, while the accessibility menu helper
    expects integer coordinates.
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        print("WARN: ChatMessageCell missing (float coordinate fix)")
        return
    t = cmc.read_text(encoding="utf-8")
    original = t
    t = t.replace(
        "int a11yX = lastTouchX > 0 ? lastTouchX : getWidth() / 2;",
        "int a11yX = lastTouchX > 0 ? (int) lastTouchX : getWidth() / 2;",
    )
    t = t.replace(
        "int a11yY = lastTouchY > 0 ? lastTouchY : getHeight() / 2;",
        "int a11yY = lastTouchY > 0 ? (int) lastTouchY : getHeight() / 2;",
    )
    if t != original:
        cmc.write_text(t, encoding="utf-8")
        print("ChatMessageCell float coordinate compile fix OK")
    else:
        print("ChatMessageCell float coordinate fix already OK/not needed")


def patch_recording_beep() -> None:
    """Install an audible cue directly at MediaController.startRecording()."""
    mc = JAVA / "org/telegram/messenger/MediaController.java"
    if not mc.exists():
        print("WARN: MediaController missing (recording beep)")
        return
    t = mc.read_text(encoding="utf-8")
    marker = "a11y-fork: recording-start beep-v2"
    if marker in t:
        print("MediaController recording-start beep v2 already patched")
        return

    # Remove the old fragile v1 implementation if a checkout was already patched.
    old = re.compile(r'\n\s*// a11y-fork: recording-start beep-wav-v1[\s\S]*?\n\s*\}\s*catch \(Throwable e\) \{\s*\n\s*FileLog\.e\(e\);\s*\n\s*\}\s*', re.MULTILINE)
    t, n = old.subn("\n", t, count=1)
    if n:
        print("Old recording beep v1 removed")

    # Anchor to Telegram's real recording entry point, not to our bitrate patch.
    sig = re.compile(r'(?m)^(?P<i>\s*)public void startRecording\(int currentAccount, long dialogId, MessageObject replyToMsg, MessageObject replyToTopMsg, TL_stories\.StoryItem replyStory, int guid, boolean manual, SendMessageChatArguments sendMessageChatArguments, long monoForumPeerId, MessageSuggestionParams suggestionParams\) \{\n')
    m = sig.search(t)
    if not m:
        print("WARN: MediaController.startRecording() declaration not found (recording beep)")
        return
    i = m.group("i") + "    "
    block = """        // a11y-fork: recording-start beep-v2 -- BEFORE Telegram starts recording
        try {
            try {
                android.content.Context a11yCtx = org.telegram.messenger.ApplicationLoader.applicationContext;
                if (a11yCtx != null) {
                    android.os.Vibrator a11yVibrator = (android.os.Vibrator) a11yCtx.getSystemService(android.content.Context.VIBRATOR_SERVICE);
                    if (a11yVibrator != null && a11yVibrator.hasVibrator()) {
                        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                            a11yVibrator.vibrate(android.os.VibrationEffect.createOneShot(50, android.os.VibrationEffect.DEFAULT_AMPLITUDE));
                        } else {
                            a11yVibrator.vibrate(50);
                        }
                    }
                }
            } catch (Throwable ignoreVibration) {}
            if (org.telegram.messenger.A11yConfig.getRecordingBeep()) {
                try {
                    android.media.ToneGenerator a11yTone = new android.media.ToneGenerator(android.media.AudioManager.STREAM_RING, 90);
                    a11yTone.startTone(android.media.ToneGenerator.TONE_PROP_BEEP, 120);
                    new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(() -> {
                        try { a11yTone.release(); } catch (Throwable ignoreRelease) {}
                    }, 160);
                } catch (Throwable beepError) {
                    org.telegram.messenger.FileLog.e(beepError);
                }
            }
        } catch (Throwable ignoreBeep) {}
"""
    block = "\n".join(i + line if line else "" for line in block.splitlines()) + "\n"
    t = t[:m.end()] + block + t[m.end():]
    mc.write_text(t, encoding="utf-8")
    print("MediaController recording-start beep v3 (ringtone stream) OK")

def patch_settings_menu() -> None:
    sa = JAVA / "org/telegram/ui/SettingsActivity.java"
    if not sa.exists():
        print("WARN: SettingsActivity missing")
        return
    t = sa.read_text(encoding="utf-8")
    needle = 'items.add(SettingCell.Factory.of(10, IconBackgroundColors.PURPLE.top, IconBackgroundColors.PURPLE.bottom, R.drawable.settings_language, getString(R.string.SettingsLanguage), LocaleController.getCurrentLanguageName()));'
    insert = needle + "\n        // a11y-fork: Accessible settings entry\n        items.add(SettingCell.Factory.of(100, IconBackgroundColors.GREEN.top, IconBackgroundColors.GREEN.bottom, R.drawable.settings_privacy, LocaleController.getString(R.string.A11yAccessibleSettings)));"
    if "a11y-fork: Accessible settings entry" not in t:
        if needle in t:
            t = t.replace(needle, insert, 1)
            print("Settings list item OK")
        else:
            print("WARN: Settings item needle not found")
    if "case 100:" not in t:
        old = """            case 10:
                presentSettingFragment(new LanguageSelectActivity());
                break;"""
        new = """            case 10:
                presentSettingFragment(new LanguageSelectActivity());
                break;
            case 100:
                // a11y-fork
                org.telegram.messenger.A11yConfig.showSettingsDialog(getParentActivity());
                break;"""
        if old in t:
            t = t.replace(old, new, 1)
            print("Settings case 100 OK")
        else:
            print("WARN: Settings case 10 block not found")
    sa.write_text(t, encoding="utf-8")


def patch_dialogcell_preview_muted_status() -> None:
    """Chat-list row text, on top of the fork's DialogCell.buildAccessibilityTextBody():
      - no "Muted" announcement at all (a topic with its own sound on is still said)
      - the contact's online / last-seen status (private chats), gated by
        A11yConfig.getShowStatusInPreview(), in place of the bare "online"
      - the message preview is read up to 300 characters instead of only what fits on screen
    """
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    if not dc.exists():
        print("WARN: DialogCell missing (preview/muted/status)")
        return
    t = dc.read_text(encoding="utf-8")
    if "a11y-fork: muted/status/preview-300" in t:
        print("DialogCell muted/status/preview-300 already patched")
        return
    old_block = (
        "        if (dialogMuted) {\n"
        "            sb.append(getString(R.string.AccDescrNotificationsMuted));\n"
        "            sb.append(\". \");\n"
        "        } else if (drawUnmute) {\n"
        "            // a topic left with its sound on inside a chat that is silent draws a mark of its own\n"
        "            sb.append(getString(R.string.AccDescrNotificationsUnmuted));\n"
        "            sb.append(\". \");\n"
        "        }\n"
        "        if (isOnline()) {\n"
        "            sb.append(getString(R.string.AccDescrUserOnline));\n"
        "            sb.append(\". \");\n"
        "        }\n"
    )
    new_block = (
        "        // a11y-fork: muted/status/preview-300 -- \"Muted\" removed, online/last-seen status\n"
        "        // announced instead when enabled.\n"
        "        if (!dialogMuted && drawUnmute) {\n"
        "            sb.append(getString(R.string.AccDescrNotificationsUnmuted));\n"
        "            sb.append(\". \");\n"
        "        }\n"
        "        if (user != null && org.telegram.messenger.A11yConfig.getShowStatusInPreview()) {\n"
        "            try {\n"
        "                String statusText = LocaleController.formatUserStatus(UserConfig.selectedAccount, user);\n"
        "                if (statusText != null && statusText.length() > 0) {\n"
        "                    sb.append(statusText);\n"
        "                    sb.append(\". \");\n"
        "                }\n"
        "            } catch (Throwable ignore) {\n"
        "            }\n"
        "        } else if (isOnline()) {\n"
        "            sb.append(getString(R.string.AccDescrUserOnline));\n"
        "            sb.append(\". \");\n"
        "        }\n"
    )
    if old_block not in t:
        print("WARN: DialogCell muted/status block not found")
        return
    t = t.replace(old_block, new_block, 1)
    old_len = (
        "            int len = messageLayout == null ? -1 : messageLayout.getText().length();\n"
        "            if (len > 0) {"
    )
    new_len = (
        "            int len = 300; // a11y-fork: read up to 300 characters, not just the visually truncated amount\n"
        "            if (len > 0 && len < messageString.length()) {"
    )
    if old_len not in t:
        print("WARN: DialogCell preview-length block not found")
    else:
        t = t.replace(old_len, new_len, 1)
    dc.write_text(t, encoding="utf-8")
    print("DialogCell muted removed / status announce / preview-300 OK")


def patch_dialogcell_time_last() -> None:
    """Sent / received sentence (and how far our own message got) is read LAST.

    The fork's buildAccessibilityTextBody() builds the row text and has several early
    returns (typing, draft, forum), so the sentence cannot simply be moved inside it.
    Instead it is cut out of there and appended by buildAccessibilityText(), the one
    wrapper every return path goes through, after the folders the chat is in.
    """
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    if not dc.exists():
        print("WARN: DialogCell missing (time-last)")
        return
    t = dc.read_text(encoding="utf-8")
    marker = "a11y-fork: preview sent-received-last v6"
    if marker in t:
        print("DialogCell sent/received LAST v6 already patched")
        return
    native = (
        "        int lastDate = lastMessageDate;\n"
        "        if (lastMessageDate == 0) {\n"
        "            lastDate = message.messageOwner.date;\n"
        "        }\n"
        "        String date = LocaleController.formatDateAudio(lastDate, true);\n"
        "        if (message.isOut()) {\n"
        "            sb.append(LocaleController.formatString(\"AccDescrSentDate\", R.string.AccDescrSentDate, date));\n"
        "        } else {\n"
        "            sb.append(LocaleController.formatString(\"AccDescrReceivedDate\", R.string.AccDescrReceivedDate, date));\n"
        "        }\n"
        "        sb.append(\". \");\n"
        "        // how far your own last message got is drawn beside the time, as a clock, one tick, two\n"
        "        // ticks or a mark in red, and none of it was ever said. A message that failed to send\n"
        "        // looked no different from one that arrived\n"
        "        if (drawError) {\n"
        "            sb.append(getString(R.string.AccDescrMsgSendingError));\n"
        "            sb.append(\". \");\n"
        "        } else if (drawClock) {\n"
        "            sb.append(getString(R.string.AccDescrMsgSending));\n"
        "            sb.append(\". \");\n"
        "        } else if (drawCheck2) {\n"
        "            sb.append(getString(drawCheck1 ? R.string.AccDescrMsgRead : R.string.AccDescrMsgUnread));\n"
        "            sb.append(\". \");\n"
        "        }\n"
    )
    if native not in t:
        print("WARN: DialogCell native sent/received block not found (time-last)")
        return
    t = t.replace(native, "        // " + marker + ": the sent/received sentence is appended by buildAccessibilityText()\n", 1)

    wrap_old = (
        "        final StringBuilder sb = (StringBuilder) buildAccessibilityTextBody();\n"
    )
    if wrap_old not in t:
        print("WARN: DialogCell buildAccessibilityText wrapper not found (time-last)")
        return
    # find the wrapper's `return sb;` (first one after the wrapper start)
    w = t.index(wrap_old)
    r = t.index("        return sb;\n", w)
    tail = (
        "        // " + marker + "\n"
        "        if (message != null && currentDialogFolderId == 0) {\n"
        "            int a11yLastDate = lastMessageDate;\n"
        "            if (lastMessageDate == 0) {\n"
        "                a11yLastDate = message.messageOwner.date;\n"
        "            }\n"
        "            String a11yPreviewDate = LocaleController.formatDateAudio(a11yLastDate, true);\n"
        "            if (message.isOut()) {\n"
        "                sb.append(LocaleController.formatString(\"AccDescrSentDate\", R.string.AccDescrSentDate, a11yPreviewDate));\n"
        "            } else {\n"
        "                sb.append(LocaleController.formatString(\"AccDescrReceivedDate\", R.string.AccDescrReceivedDate, a11yPreviewDate));\n"
        "            }\n"
        "            sb.append(\". \");\n"
        "            if (drawError) {\n"
        "                sb.append(getString(R.string.AccDescrMsgSendingError));\n"
        "                sb.append(\". \");\n"
        "            } else if (drawClock) {\n"
        "                sb.append(getString(R.string.AccDescrMsgSending));\n"
        "                sb.append(\". \");\n"
        "            } else if (drawCheck2) {\n"
        "                sb.append(getString(drawCheck1 ? R.string.AccDescrMsgRead : R.string.AccDescrMsgUnread));\n"
        "                sb.append(\". \");\n"
        "            }\n"
        "        }\n"
    )
    t = t[:r] + tail + t[r:]
    dc.write_text(t, encoding="utf-8")
    print("DialogCell sent/received LAST v6 OK")



def patch_locale_controller_solar_date_chat() -> None:
    """Solar Hijri for every chat date separator, in Telegram's own short/full format.

    Telegram builds ALL of these strings (in-list date dividers, the floating date
    header, scheduled-date text, ...) with the single shared
    LocaleController.formatDateChat(date, checkYear). The in-list dividers are
    ChatActionCell instances whose text comes from MessageObject.messageText, NOT from
    ChatActionCell.setCustomDate(), so patching ChatActionCell alone (previous
    revisions) never reached what TalkBack actually reads. Patching the one shared
    formatter fixes every caller at once and keeps Telegram's exact "short form inside
    the last year, full form with year otherwise" decision.
    """
    lc = JAVA / "org/telegram/messenger/LocaleController.java"
    if not lc.exists():
        print("WARN: LocaleController missing (solar date chat)")
        return
    t = lc.read_text(encoding="utf-8")
    marker = "a11y-fork: solar formatDateChat v1"
    if marker in t:
        print("LocaleController solar formatDateChat already patched")
        return
    old = "    public static String formatDateChat(long date, boolean checkYear) {\n"
    new = (
        old +
        "        // " + marker + "\n"
        "        try {\n"
        "            if (A11yConfig.getSolarCalendar()) {\n"
        "                String a11ySolar = A11yConfig.formatSolarDateChat(date, checkYear);\n"
        "                if (a11ySolar != null && a11ySolar.length() > 0) {\n"
        "                    return a11ySolar;\n"
        "                }\n"
        "            }\n"
        "        } catch (Throwable ignore) {\n"
        "        }\n"
    )
    if t.count(old) != 1:
        print("WARN: LocaleController.formatDateChat(long, boolean) anchor not found exactly once")
        return
    lc.write_text(t.replace(old, new, 1), encoding="utf-8")
    print("LocaleController solar formatDateChat OK")


def patch_solar_last_seen() -> None:
    """Solar Hijri for "last seen" (LocaleController.formatDateOnline).

    With the Solar calendar setting on, the date inside "last seen <date> at <time>" (chat header,
    profile, contact lists) is shown in Solar Hijri, like the chat's date separators: short form
    ("21 Mehr") inside the last year, with the year ("21 Mehr, 1403") when older. "today" and
    "yesterday" are unchanged, and the time part is untouched. Off: the original Gregorian text.
    """
    lc = JAVA / "org/telegram/messenger/LocaleController.java"
    old = (
        "            } else if (Math.abs(System.currentTimeMillis() - date) < 31536000000L) {\n"
        "                String format = LocaleController.formatString(\"formatDateAtTime\", R.string.formatDateAtTime, getInstance().getFormatterDayMonth().format(new Date(date)), getInstance().getFormatterDay().format(new Date(date)));\n"
        "                return LocaleController.formatString(\"LastSeenDateFormatted\", R.string.LastSeenDateFormatted, format);\n"
        "            } else {\n"
        "                String format = LocaleController.formatString(\"formatDateAtTime\", R.string.formatDateAtTime, getInstance().getFormatterYear().format(new Date(date)), getInstance().getFormatterDay().format(new Date(date)));\n"
        "                return LocaleController.formatString(\"LastSeenDateFormatted\", R.string.LastSeenDateFormatted, format);\n"
        "            }\n"
    )
    new = (
        "            } else if (Math.abs(System.currentTimeMillis() - date) < 31536000000L) {\n"
        "                String a11yDate = null; // a11y-fork: solar last seen\n"
        "                try {\n"
        "                    if (A11yConfig.getSolarCalendar()) {\n"
        "                        a11yDate = A11yConfig.formatSolarDateChat(date / 1000L, false);\n"
        "                    }\n"
        "                } catch (Throwable ignore) {\n"
        "                }\n"
        "                String format = LocaleController.formatString(\"formatDateAtTime\", R.string.formatDateAtTime, (a11yDate != null && a11yDate.length() > 0) ? a11yDate : getInstance().getFormatterDayMonth().format(new Date(date)), getInstance().getFormatterDay().format(new Date(date)));\n"
        "                return LocaleController.formatString(\"LastSeenDateFormatted\", R.string.LastSeenDateFormatted, format);\n"
        "            } else {\n"
        "                String a11yDate = null; // a11y-fork: solar last seen\n"
        "                try {\n"
        "                    if (A11yConfig.getSolarCalendar()) {\n"
        "                        a11yDate = A11yConfig.formatSolarDateChat(date / 1000L, false);\n"
        "                    }\n"
        "                } catch (Throwable ignore) {\n"
        "                }\n"
        "                String format = LocaleController.formatString(\"formatDateAtTime\", R.string.formatDateAtTime, (a11yDate != null && a11yDate.length() > 0) ? a11yDate : getInstance().getFormatterYear().format(new Date(date)), getInstance().getFormatterDay().format(new Date(date)));\n"
        "                return LocaleController.formatString(\"LastSeenDateFormatted\", R.string.LastSeenDateFormatted, format);\n"
        "            }\n"
    )
    _gate_once(lc, old, new, "LocaleController solar last seen")


def patch_hide_sponsor_channel() -> None:
    """
    Accessibility-fork: when A11yConfig.getHideSponsorChannel() is on,
    automatically hide the proxy sponsor/promo channel from the chat list
    using Telegram's own existing hidePromoDialog() mechanism, checked each
    time the chat list resumes.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    if not da.exists():
        print("WARN: DialogsActivity missing (hide sponsor channel)")
        return
    t = da.read_text(encoding="utf-8")
    if "a11y-fork: hide sponsor channel" in t:
        print("DialogsActivity hide-sponsor-channel already patched")
        return
    old = (
        "    public void onResume() {\n"
        "        super.onResume();\n"
    )
    new = (
        "    public void onResume() {\n"
        "        super.onResume();\n"
        "        // a11y-fork: hide sponsor channel\n"
        "        try {\n"
        "            if (org.telegram.messenger.A11yConfig.getHideSponsorChannel()) {\n"
        "                getMessagesController().hidePromoDialog();\n"
        "            }\n"
        "        } catch (Throwable ignore) {\n"
        "        }\n"
    )
    if old not in t:
        print("WARN: DialogsActivity onResume anchor not found (hide sponsor channel)")
        return
    t = t.replace(old, new, 1)
    da.write_text(t, encoding="utf-8")
    print("DialogsActivity hide-sponsor-channel OK")


def patch_ghost_mode() -> None:
    """
    Accessibility-fork: Ghost Mode -- when A11yConfig.getGhostMode() is on, the client never tells the
    server that messages were read, so senders never see "seen".  It is done in ONE place,
    MessagesController.completeReadTask: every read receipt (private chats, groups, channels, comment
    threads, saved/monoforum chats, secret chats) is sent from there.  markDialogAsRead still runs, so the
    unread counter and notifications are cleared LOCALLY (the chat does not show the same unread messages
    again after you read them).  The server keeps its old "read" position, so the counter may come back
    after a full refresh from the server.
    """
    mc = JAVA / "org/telegram/messenger/MessagesController.java"
    _gate_once(
        mc,
        "    private void completeReadTask(ReadTask task) {\n",
        "    private void completeReadTask(ReadTask task) {\n"
        "        if (A11yConfig.getGhostMode()) { // a11y-fork: ghost mode -- never send read receipts\n"
        "            return;\n"
        "        }\n",
        "MessagesController ghost mode (read receipts)")



def patch_links_as_menu() -> None:
    # Optional Links item at the end of the accessibility message-menu tail.
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (links menu)")
        return
    t = ca.read_text(encoding="utf-8")
    marker = "a11y-fork: links menu v1"
    if marker in t:
        return
    if "a11y-fork: OPTION_LINKS_MENU declaration" not in t:
        idx=t.find("public class ChatActivity")
        if idx>=0:
            brace=t.find("{",idx)
            if brace>=0:
                t=t[:brace+1]+"\n    private static final int OPTION_LINKS_MENU = 206; // a11y-fork: OPTION_LINKS_MENU declaration\n"+t[brace+1:]
    bot_anchor='        // a11y-fork: bot buttons menu\n        if (message != null && message.hasInlineBotButtons()) {'
    links_item='''        // a11y-fork: links menu v1
        if (org.telegram.messenger.A11yConfig.getLinksMenuEnabled() && message != null && a11yMessageHasLinks(message)) {
            items.add(LocaleController.getString(R.string.A11yLinks));
            options.add(OPTION_LINKS_MENU);
            icons.add(R.drawable.msg_forward);
        }

'''
    if bot_anchor not in t:
        print("WARN: Bot Buttons anchor not found; Links item not inserted")
        ca.write_text(t,encoding="utf-8")
        return
    t=t.replace(bot_anchor,links_item+bot_anchor,1)
    helper_anchor='    private void fillMessageMenu(ArrayList<CharSequence> items, ArrayList<Integer> options, ArrayList<Integer> icons, MessageObject message) {'
    helper='''    // a11y-fork: links menu helper
    private boolean a11yMessageHasLinks(MessageObject message) {
        if (message == null || message.messageOwner == null) return false;
        try {
            if (message.messageOwner.entities != null) {
                for (TLRPC.MessageEntity e : message.messageOwner.entities) {
                    if (e instanceof TLRPC.TL_messageEntityUrl || e instanceof TLRPC.TL_messageEntityTextUrl || e instanceof TLRPC.TL_messageEntityEmail || e instanceof TLRPC.TL_messageEntityMention || e instanceof TLRPC.TL_messageEntityMentionName) return true;
                }
            }
            String raw = message.messageOwner.message;
            return raw != null && raw.matches("(?s).*https?://[^\\\\s]+.*");
        } catch (Throwable ignore) { return false; }
    }

    private void a11yShowMessageLinks(MessageObject message) {
        try {
            java.util.ArrayList<String> links = new java.util.ArrayList<>();
            java.util.ArrayList<String> a11yLabels = new java.util.ArrayList<>(); // what the menu shows: the link as the author wrote it
            String raw = message != null && message.messageOwner != null ? message.messageOwner.message : null;
            if (raw == null) raw = "";
            if (message != null && message.messageOwner != null && message.messageOwner.entities != null) {
                for (TLRPC.MessageEntity e : message.messageOwner.entities) {
                    String url = null;
                    String a11yLabel = null;
                    if (e instanceof TLRPC.TL_messageEntityTextUrl) {
                        url = ((TLRPC.TL_messageEntityTextUrl)e).url;
                        a11yLabel = url;
                    } else if (e instanceof TLRPC.TL_messageEntityUrl || e instanceof TLRPC.TL_messageEntityEmail) {
                        int s=Math.max(0,Math.min(raw.length(),e.offset));
                        int end=Math.max(s,Math.min(raw.length(),s+e.length));
                        url=raw.substring(s,end);
                        a11yLabel = url; // as written: no https:// / mailto: added
                        if (e instanceof TLRPC.TL_messageEntityEmail) url="mailto:"+url;
                        else {
                            String a11yLow = url.toLowerCase();
                            if (!a11yLow.contains("://") && !a11yLow.startsWith("tg:") && !a11yLow.startsWith("mailto:")) url="https://"+url;
                        }
                    } else if (e instanceof TLRPC.TL_messageEntityMention) {
                        // a11y-fork: @username mention -> t.me deep link
                        int s=Math.max(0,Math.min(raw.length(),e.offset));
                        int end=Math.max(s,Math.min(raw.length(),s+e.length));
                        String uname=raw.substring(s,end);
                        a11yLabel = uname; // as written, with the @
                        if (uname.startsWith("@")) uname=uname.substring(1);
                        if (uname.length()>0) url="https://t.me/"+uname;
                    } else if (e instanceof TLRPC.TL_messageEntityMentionName) {
                        // a11y-fork: tap-to-profile mention (no @ in raw text) -> t.me deep link by user id
                        long uid = ((TLRPC.TL_messageEntityMentionName)e).user_id;
                        if (uid != 0) {
                            url="tg://user?id="+uid;
                            int s=Math.max(0,Math.min(raw.length(),e.offset));
                            int end=Math.max(s,Math.min(raw.length(),s+e.length));
                            a11yLabel = raw.substring(s,end);
                        }
                    }
                    if (url != null && url.length()>0 && !links.contains(url)) {
                        links.add(url);
                        a11yLabels.add(a11yLabel != null && a11yLabel.trim().length() > 0 ? a11yLabel : url);
                    }
                }
            }
            java.util.regex.Matcher m=java.util.regex.Pattern.compile("https?://[^\\\\s<>\\"]+").matcher(raw);
            while(m.find()) {
                String url=m.group();
                while(url.endsWith(".")||url.endsWith(",")||url.endsWith(")")||url.endsWith("]")) url=url.substring(0,url.length()-1);
                if(url.length()>0&&!links.contains(url)) { links.add(url); a11yLabels.add(url); }
            }
            if(links.isEmpty()) {
                if(getParentActivity()!=null) getParentActivity().getWindow().getDecorView().announceForAccessibility(LocaleController.getString(R.string.A11yNoLinks));
                return;
            }
            final String[] values=links.toArray(new String[0]);
            final String[] a11yShown=a11yLabels.toArray(new String[0]);
            new AlertDialog.Builder(getParentActivity()).setTitle(LocaleController.getString(R.string.A11yLinks)).setItems(a11yShown,(dialog,which)->{
                if(which>=0&&which<values.length) {
                    // a11y-fork: Telegram's own links (t.me / telegram.me / telegram.dog / tg://) must be
                    // handled INSIDE Telegram (same path a normal tap on such a link takes), never handed
                    // to the system browser. Everything else keeps the previous external behaviour.
                    final String a11yUrl = values[which];
                    boolean a11yInternal = false;
                    try { a11yInternal = Browser.isInternalUrl(a11yUrl, null); } catch (Throwable ignore) {}
                    if (a11yInternal) {
                        try { Browser.openUrl(getParentActivity(), android.net.Uri.parse(a11yUrl)); }
                        catch(Throwable e){ FileLog.e(e); }
                    } else {
                        try { getParentActivity().startActivity(new android.content.Intent(android.content.Intent.ACTION_VIEW,android.net.Uri.parse(a11yUrl))); }
                        catch(Throwable e){ FileLog.e(e); }
                    }
                }
            }).setNegativeButton(LocaleController.getString(R.string.A11yCancel),null).show();
        } catch(Throwable e) { FileLog.e(e); }
    }

'''
    fmm_idx = t.find("public void fillMessageMenu(")
    if fmm_idx == -1:
        fmm_idx = t.find(helper_anchor)
    if fmm_idx >= 0:
        t = t[:fmm_idx] + helper + t[fmm_idx:]
    else:
        print("WARN: fillMessageMenu anchor not found")
    case_anchor='            case OPTION_BOT_BUTTONS_MENU: {'
    case='''            case OPTION_LINKS_MENU: { // a11y-fork: links menu handler
                a11yShowMessageLinks(selectedObject);
                selectedObject=null;
                selectedObjectToEditCaption=null;
                selectedObjectGroup=null;
                break;
            }
'''
    if case_anchor in t: t=t.replace(case_anchor,case+case_anchor,1)
    else: print("WARN: Bot Buttons handler anchor not found")
    ca.write_text(t,encoding="utf-8")
    print("ChatActivity optional Links menu OK")


def patch_bot_buttons_menu() -> None:
    """
    Accessibility-fork: fold scattered inline bot buttons (Connect/Close/
    Open etc.) under each message bubble into a single "Bot Buttons" item
    in the message options menu, opening a picker dialog instead.
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not cmc.exists() or not ca.exists():
        print("WARN: ChatMessageCell/ChatActivity missing (bot buttons menu)")
        return

    # 1) Hide the inline bot-button row under the bubble.
    t = cmc.read_text(encoding="utf-8")
    if "a11y-fork: bot buttons menu" in t:
        print("ChatMessageCell bot-buttons-menu already patched")
    else:
        old = (
            "            final int separatorHeight = dp(4 + 4);\n"
            "            if (!messageObject.isRestrictedMessage && !messageObject.isRepostPreview "
            "&& (currentPosition == null || currentMessagesGroup != null && currentMessagesGroup.isDocuments "
            "&& currentPosition.last) && (inlineButtons != null) && !messageObject.hasExtendedMedia()) {\n"
        )
        new = (
            "            final int separatorHeight = dp(4 + 4);\n"
            "            // a11y-fork: bot buttons menu -- inline bot buttons under\n"
            "            // the bubble are hidden from TalkBack; use the \"Bot Buttons\"\n"
            "            // message menu item instead.\n"
            "            if (false && !messageObject.isRestrictedMessage && !messageObject.isRepostPreview "
            "&& (currentPosition == null || currentMessagesGroup != null && currentMessagesGroup.isDocuments "
            "&& currentPosition.last) && (inlineButtons != null) && !messageObject.hasExtendedMedia()) {\n"
        )
        if old not in t:
            print("WARN: ChatMessageCell inline-bot-buttons anchor not found")
        else:
            t = t.replace(old, new, 1)
            cmc.write_text(t, encoding="utf-8")
            print("ChatMessageCell bot-buttons-menu hide OK")

    # 2) Add the "Bot Buttons" menu item + its click handler in ChatActivity.
    t2 = ca.read_text(encoding="utf-8")
    # a11y-fork: OPTION_BOT_BUTTONS_MENU must be a Java field, not only a
    # Python-side constant.  The menu item and handler below both reference it.
    if "a11y-fork: OPTION_BOT_BUTTONS_MENU declaration" not in t2:
        class_anchor = "public class ChatActivity"
        class_idx = t2.find(class_anchor)
        if class_idx != -1:
            brace_idx = t2.find("{", class_idx)
            if brace_idx != -1:
                t2 = (
                    t2[:brace_idx + 1]
                    + "\n    private static final int OPTION_BOT_BUTTONS_MENU = 205; // a11y-fork: OPTION_BOT_BUTTONS_MENU declaration\n"
                    + t2[brace_idx + 1:]
                )
                print("ChatActivity OPTION_BOT_BUTTONS_MENU declaration OK")
            else:
                print("WARN: ChatActivity class opening brace not found (bot buttons menu)")
        else:
            print("WARN: ChatActivity class declaration not found (bot buttons menu)")

    if "a11y-fork: bot buttons menu" in t2:
        print("ChatActivity bot-buttons-menu already patched")
        ca.write_text(t2, encoding="utf-8")
        return

    old_item = (
        "        if (message.isSponsored() && !getUserConfig().isPremium() "
        "&& !getMessagesController().premiumFeaturesBlocked() && !message.sponsoredCanReport) {\n"
    )
    new_item = (
        "        // a11y-fork: bot buttons menu\n"
        "        if (message != null && message.hasInlineBotButtons()) {\n"
        "            items.add(\"Bot Buttons\");\n"
        "            options.add(OPTION_BOT_BUTTONS_MENU);\n"
        "            icons.add(R.drawable.msg_viewreplies);\n"
        "        }\n"
        "\n"
        "        if (message.isSponsored() && !getUserConfig().isPremium() "
        "&& !getMessagesController().premiumFeaturesBlocked() && !message.sponsoredCanReport) {\n"
    )
    if old_item not in t2:
        print("WARN: ChatActivity sponsored-item anchor not found (bot buttons menu item)")
        return
    t2 = t2.replace(old_item, new_item, 1)

    old_case = "            case OPTION_RETRY: {\n"
    new_case = (
        "            case OPTION_BOT_BUTTONS_MENU: {\n"
        "                try {\n"
        "                    MessageObject msg = selectedObject;\n"
        "                    ArrayList<CharSequence> labels = new ArrayList<>();\n"
        "                    ArrayList<TL_keyboard.KeyboardInlineButton> btns = new ArrayList<>();\n"
        "                    if (msg != null && msg.messageOwner != null && msg.messageOwner.reply_markup "
        "instanceof TLRPC.TL_replyInlineMarkup) {\n"
        "                        TLRPC.TL_replyInlineMarkup markup = (TLRPC.TL_replyInlineMarkup) msg.messageOwner.reply_markup;\n"
        "                        for (int b = 0; b < markup.rows.size(); b++) {\n"
        "                            TL_keyboard.KeyboardInlineButtonRow row = markup.rows.get(b);\n"
        "                            for (int c = 0; c < row.buttons.size(); c++) {\n"
        "                                TL_keyboard.KeyboardInlineButton btn = row.buttons.get(c);\n"
        "                                CharSequence label = !TextUtils.isEmpty(btn.text) ? btn.text : (\"Bot \" + (labels.size() + 1));\n"
        "                                labels.add(label);\n"
        "                                btns.add(btn);\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                    if (!labels.isEmpty() && getParentActivity() != null) {\n"
        "                        CharSequence[] itemsArr = labels.toArray(new CharSequence[0]);\n"
        "                        final MessageObject msgFinal = msg;\n"
        "                        final ArrayList<TL_keyboard.KeyboardInlineButton> btnsFinal = btns;\n"
        "                        AlertDialog.Builder botBtnBuilder = new AlertDialog.Builder(getParentActivity());\n"
        "                        botBtnBuilder.setTitle(\"Bot Buttons\");\n"
        "                        botBtnBuilder.setItems(itemsArr, (dialog, which) -> {\n"
        "                            if (which >= 0 && which < btnsFinal.size() && chatActivityEnterView != null) {\n"
        "                                chatActivityEnterView.didPressedBotButton(btnsFinal.get(which), msgFinal, msgFinal);\n"
        "                            }\n"
        "                        });\n"
        "                        botBtnBuilder.setNegativeButton(LocaleController.getString(R.string.Cancel), null);\n"
        "                        showDialog(botBtnBuilder.create());\n"
        "                    }\n"
        "                } catch (Throwable e) {\n"
        "                    FileLog.e(e);\n"
        "                }\n"
        "                selectedObject = null;\n"
        "                selectedObjectGroup = null;\n"
        "                break;\n"
        "            }\n"
        "            case OPTION_RETRY: {\n"
    )
    if old_case not in t2:
        print("WARN: ChatActivity OPTION_RETRY case anchor not found (bot buttons menu handler)")
        return
    t2 = t2.replace(old_case, new_case, 1)

    ca.write_text(t2, encoding="utf-8")
    print("ChatActivity bot-buttons-menu item+handler OK")



def patch_go_to_first_message() -> None:
    """Add a localized "Go to first message" action to the chat's top-right "..." menu.

    It reuses Telegram's own date jump (ChatActivity.jumpToDate -- the code behind the calendar's
    "Jump to date") with the earliest possible date: if the start of the chat is already loaded
    it scrolls straight to the oldest message, otherwise the server positions the chat on the
    very first messages (messages.getHistory with offset_date). The old version loaded pages with
    load_type 1, which is Telegram's "newer messages" direction, so it walked toward the LATEST
    message instead of the first one (and message id 1 is not the first message of a chat anyway:
    ids are global per account in private chats and groups).
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (go to first message)")
        return
    t = ca.read_text(encoding="utf-8")

    if "a11y-fork: OPTION_GO_TO_FIRST_MESSAGE declaration" not in t:
        anchor = "    private final static int id_chat_compose_panel = 1000;"
        if anchor in t:
            t = t.replace(anchor, anchor + "\n    private final static int OPTION_GO_TO_FIRST_MESSAGE = 75; // a11y-fork: OPTION_GO_TO_FIRST_MESSAGE declaration", 1)
        else:
            print("WARN: go-to-first-message declaration anchor not found")

    if "a11y-fork: go-to-first-message helper" not in t:
        anchor = "    public void firstLoadMessages() {"
        helper = """    // a11y-fork: go-to-first-message helper (v2: Telegram's own date jump to the earliest date)
    private void accessibilityGoToFirstMessage() {
        if (dialog_id == 0 || isTopic) {
            return;
        }
        wasManualScroll = true;
        try {
            jumpToDate(1);
        } catch (Throwable e) {
            FileLog.e(e);
        }
    }

"""
        if anchor in t:
            t = t.replace(anchor, helper + anchor, 1)
        else:
            print("WARN: go-to-first-message helper anchor not found")

    if "a11y-fork: go-to-first-message menu" not in t:
        # FIRST item of the chat's top-right "..." menu: inserted right after the menu is
        # created (before Saved-chats / Call / Search / ...), not after "view as topics".
        anchor = ("            headerItem.setContentDescription(LocaleController.getString(R.string.AccDescrMoreOptions));\n\n"
                  "            if (currentUser != null && currentUser.self && chatMode != MODE_SAVED) {\n")
        insert = ("            headerItem.setContentDescription(LocaleController.getString(R.string.AccDescrMoreOptions));\n"
                  "            if (dialog_id != 0 && !isTopic && chatMode != MODE_SAVED && (currentUser == null || !currentUser.self)) {\n"
                  "                // a11y-fork: go-to-first-message menu\n"
                  "                headerItem.lazilyAddSubItem(OPTION_GO_TO_FIRST_MESSAGE, R.drawable.msg_search, LocaleController.getString(R.string.A11yGoToFirstMessage));\n"
                  "            }\n\n"
                  "            if (currentUser != null && currentUser.self && chatMode != MODE_SAVED) {\n")
        if t.count(anchor) == 1:
            t = t.replace(anchor, insert, 1)
        else:
            print("WARN: go-to-first-message first-position anchor found %d times" % t.count(anchor))

    if "a11y-fork: go-to-first-message handler" not in t:
        anchor = "                } else if (id == view_as_topics) {"
        branch = ("                } else if (id == OPTION_GO_TO_FIRST_MESSAGE) { // a11y-fork: go-to-first-message handler\n"
                  "                    accessibilityGoToFirstMessage();\n"
                  "                } else if (id == view_as_topics) {")
        if anchor in t:
            t = t.replace(anchor, branch, 1)
        else:
            print("WARN: go-to-first-message handler anchor not found")

    ca.write_text(t, encoding="utf-8")
    print("ChatActivity go-to-first-message OK")


def patch_file_description_spacing() -> None:
    """TalkBack: announce the real document filename as a single clean "file <name>" (with a real
    space, never concatenated), not Telegram's internal numeric storage filename and not a
    separate/duplicated extension-type announcement (which read out of order and could confuse
    TalkBack's long-press gesture)."""
    cmc=JAVA/"org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        print("WARN: ChatMessageCell missing (file description spacing)"); return
    t=cmc.read_text(encoding="utf-8")
    marker="a11y-fork: real document filename"
    # Clean up: if an older revision of this patch (with the redundant extension-type
    # announcement) already applied, replace it with the simplified single-announcement version.
    old_verbose = (
        "                    if (documentAttach != null && documentAttachType == DOCUMENT_ATTACH_TYPE_DOCUMENT) {\n"
        "                        // a11y-fork: real document filename\n"
        "                        String a11yDocumentName = FileLoader.getDocumentFileName(documentAttach);\n"
        "                        if (!TextUtils.isEmpty(a11yDocumentName)) {\n"
        "                            sb.append(a11yDocumentName);\n"
        "                            sb.append(\". \");\n"
        "                            String a11yExtension = a11yDocumentName;\n"
        "                            int a11yDot = a11yExtension.lastIndexOf('.');\n"
        "                            if (a11yDot >= 0 && a11yDot + 1 < a11yExtension.length()) {\n"
        "                                a11yExtension = a11yExtension.substring(a11yDot + 1).toUpperCase(Locale.ROOT);\n"
        "                                sb.append(formatString(R.string.AccDescrDocumentType, a11yExtension));\n"
        "                                sb.append(\" \");\n"
        "                            }\n"
        "                        }\n"
        "                    }")
    if old_verbose in t:
        t = t.replace(old_verbose, "", 1)  # drop; the block below (re)inserts the clean version

    if marker not in t:
        old=(
            "                    if (documentAttach != null && documentAttachType == DOCUMENT_ATTACH_TYPE_DOCUMENT) {\n"
            "                        String fileName = FileLoader.getAttachFileName(documentAttach);\n"
            "                        if (fileName.indexOf('.') != -1) {\n"
            "                            sb.append(formatString(R.string.AccDescrDocumentType, fileName.substring(fileName.lastIndexOf('.') + 1).toUpperCase(Locale.ROOT)));\n"
            "                        }\n"
            "                    }")
        new=(
            "                    if (documentAttach != null && documentAttachType == DOCUMENT_ATTACH_TYPE_DOCUMENT) {\n"
            "                        // a11y-fork: real document filename -- single \"File: <name>\" announcement,\n"
            "                        // built as one literal Java string so \"File\" can never end up glued to\n"
            "                        // the filename (that broke TalkBack reading and its long-press gesture).\n"
            "                        // Telegram sets messageText to the filename itself when a document has\n"
            "                        // no separate caption, and the untouched native code just below (which\n"
            "                        // appends messageText) would then read that same filename a second time --\n"
            "                        // so when that's about to happen, say only \"File:\" here and let that\n"
            "                        // native code supply the name once (still followed by its file size).\n"
            "                        String a11yDocumentName = FileLoader.getDocumentFileName(documentAttach);\n"
            "                        if (!TextUtils.isEmpty(a11yDocumentName)) {\n"
            "                            boolean a11yNameWillRepeat = !TextUtils.isEmpty(currentMessageObject.messageText)\n"
            "                                    && currentMessageObject.messageText.toString().trim().equals(a11yDocumentName.trim());\n"
            "                            sb.append(getString(R.string.A11yFileLabel));\n"
            "                            sb.append(\": \");\n"
            "                            if (!a11yNameWillRepeat) {\n"
            "                                sb.append(a11yDocumentName);\n"
            "                                sb.append(\". \");\n"
            "                            }\n"
            "                        }\n"
            "                    }")
        if old in t:
            t=t.replace(old,new,1); cmc.write_text(t,encoding="utf-8"); print("ChatMessageCell single clean \"file <name>\" announcement OK")
        else: print("WARN: ChatMessageCell document accessibility anchor not found")
    else:
        cmc.write_text(t,encoding="utf-8")
        print("ChatMessageCell real document filename already patched")
    # AccDescrDocumentType is no longer referenced by the patched block above
    # (the clean "file <name>" text is built directly in Java), so it's left untouched.

def patch_chat_message_cell_accessibility_long_click() -> None:
    """Route TalkBack long-clicks from ChatMessageCell host and virtual nodes."""
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        return
    t = cmc.read_text(encoding="utf-8")
    marker = "a11y-fork: accessibility-long-click-v2"
    if marker in t:
        return
    host = "        if (action == AccessibilityNodeInfo.ACTION_CLICK) {\n"
    host_new = (
        "        // " + marker + "\n"
        "        if (action == AccessibilityNodeInfo.ACTION_LONG_CLICK) {\n"
        "            try {\n"
        "                if (delegate != null && currentMessageObject != null) {\n"
        "                    float a11yX = lastTouchX > 0 ? lastTouchX : getWidth() / 2f;\n"
        "                    float a11yY = lastTouchY > 0 ? lastTouchY : getHeight() / 2f;\n"
        "                    delegate.didLongPress(ChatMessageCell.this, a11yX, a11yY);\n"
        "                    return true;\n"
        "                }\n"
        "            } catch (Throwable e) { FileLog.e(e); }\n"
        "            return true;\n"
        "        } else if (action == AccessibilityNodeInfo.ACTION_CLICK) {\n"
    )
    if host not in t:
        print("WARN: host long-click anchor missing")
        return
    t = t.replace(host, host_new, 1)
    prov = "            if (virtualViewId == HOST_VIEW_ID) {\n                performAccessibilityAction(action, arguments);\n            } else {\n"
    prov_new = (
        "            if (virtualViewId == HOST_VIEW_ID) {\n"
        "                performAccessibilityAction(action, arguments);\n"
        "            } else {\n"
        "                // " + marker + " virtual node\n"
        "                if (action == AccessibilityNodeInfo.ACTION_LONG_CLICK) {\n"
        "                    try {\n"
        "                        if (delegate != null && currentMessageObject != null) {\n"
        "                            // the reply / forward header is part of the message, not a place of its own:\n"
        "                            // a long press there must open the message options, at the middle of the message\n"
        "                            final boolean a11yCenter = true;\n"
        "                            float a11yX = !a11yCenter && lastTouchX > 0 ? lastTouchX : getWidth() / 2f;\n"
        "                            float a11yY = !a11yCenter && lastTouchY > 0 ? lastTouchY : getHeight() / 2f;\n"
        "                            delegate.didLongPress(ChatMessageCell.this, a11yX, a11yY);\n"
        "                            sendAccessibilityEventForVirtualView(virtualViewId, AccessibilityEvent.TYPE_VIEW_LONG_CLICKED);\n"
        "                            return true;\n"
        "                        }\n"
        "                    } catch (Throwable e) { FileLog.e(e); }\n"
        "                    return true;\n"
        "                }\n"
    )
    if prov not in t:
        print("WARN: provider long-click anchor missing")
        return
    t = t.replace(prov, prov_new, 1)
    cmc.write_text(t, encoding="utf-8")
    print("ChatMessageCell accessibility long-click v2 OK")

def patch_fork_selection_vs_options() -> None:
    """Reconcile the fork's message-selection actions with this project's Message Options.

    The fork makes an accessibility long-click on a message START CHOOSING messages (and
    labels the action "enter selection mode"). Here a long-click must open the Message
    Options menu (Select is an item of that menu). While messages are already being
    chosen (check box visible) the fork's behaviour is kept: click / long-click toggle.
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        print("WARN: ChatMessageCell missing (selection vs options)")
        return
    t = cmc.read_text(encoding="utf-8")
    marker = "a11y-fork: long-click opens Message Options"
    if marker in t:
        print("ChatMessageCell selection-vs-options already patched")
        return
    old = (
        "        if (!checkBoxVisible && action != AccessibilityNodeInfo.ACTION_LONG_CLICK) {\n"
        "            return false;\n"
        "        }\n"
    )
    new = (
        "        // " + marker + ": outside selection mode both click and long-click are left to the\n"
        "        // normal paths (long-click -> didLongPress -> Message Options menu)\n"
        "        if (!checkBoxVisible) {\n"
        "            return false;\n"
        "        }\n"
    )
    if old not in t:
        print("WARN: fork selection anchor not found (selection vs options)")
        return
    t = t.replace(old, new, 1)
    old_lbl = 'info.addAction(new AccessibilityNodeInfo.AccessibilityAction(AccessibilityNodeInfo.ACTION_LONG_CLICK, getString("AccActionEnterSelectionMode", R.string.AccActionEnterSelectionMode)));'
    new_lbl = 'info.addAction(new AccessibilityNodeInfo.AccessibilityAction(AccessibilityNodeInfo.ACTION_LONG_CLICK, getString("AccActionMessageOptions", R.string.AccActionMessageOptions)));'
    if old_lbl in t:
        t = t.replace(old_lbl, new_lbl, 1)
    else:
        print("WARN: fork long-click label anchor not found (selection vs options)")
    cmc.write_text(t, encoding="utf-8")
    print("ChatMessageCell selection-vs-options OK")


def patch_mehran_strings_persian() -> None:
    """Persian text for the strings the fork adds (Telegram's server language pack has none of
    them, so without this a Persian TTS voice would spell out English words)."""
    fa = {
        'AccActionChartOpenDay': 'نمایش این روز',
        'VoipShareScreenTitle': 'اشتراک\u200cگذاری صفحه',
        'VoipShareScreenAudio': 'صدای گوشی هم به اشتراک گذاشته شود',
        'VoipShareScreenAudioInfo': 'ویدیوها، موسیقی و هر صدایی که برنامه\u200cها پخش می\u200cکنند همراه با صفحه\u200cی شما در تماس شنیده می\u200cشود. برخی برنامه\u200cها اجازه نمی\u200cدهند صدایشان به اشتراک گذاشته شود.',
        'SecretChatAccessibilityTitle': 'این چت مخفی خوانده شود؟',
        'SecretChatAccessibilityText': 'چت\u200cهای مخفی از سرویس\u200cهای دسترس\u200cپذیری پنهان نگه داشته می\u200cشوند، چون هر سرویسی که روی این گوشی روشن باشد می\u200cتواند آنچه روی صفحه است را بخواند. سرویس\u200cهای روشن فعلی: %1$s.\\n\\nاگر ادامه بدهید، این سرویس\u200cها می\u200cتوانند پیام\u200cهای این چت را بخوانند و به %2$s هم در چت خبر داده می\u200cشود.',
        'SecretChatAccessibilityAllow': 'اجازه بده و خبر بده',
        'SecretChatAccessibilityWarning': 'من با صفحه\u200cخوان کار می\u200cکنم، برای همین به سرویس\u200cهای دسترس\u200cپذیری گوشی\u200cام اجازه دادم این چت مخفی را بخوانند: %1$s. هر چیزی که روی صفحه ببینند می\u200cتوانند بخوانند.',
        'AccActionLinkOptions': 'گزینه\u200cهای %1$s',
        'AccActionSenderOptions': 'گزینه\u200cهای فرستنده',
        'AccActionReactWith': 'واکنش با %1$s',
        'AccActionUnreactWith': 'حذف واکنش %1$s',
        'AccActionReactWithCount_one': 'واکنش با %2$s، %1$d نفر',
        'AccActionReactWithCount_other': 'واکنش با %2$s، %1$d نفر',
        'AccActionUnreactWithCount_one': 'حذف واکنش %2$s، %1$d نفر',
        'AccActionUnreactWithCount_other': 'حذف واکنش %2$s، %1$d نفر',
        'AccActionOpenCommunity': 'باز کردن کامیونیتی',
        'AccDescrCurvesTool': 'منحنی\u200cها',
        'AccDescrColorPicker': 'انتخاب رنگ',
        'AccDescrFlashlight': 'چراغ قوه',
        'AccDescrInsertIntoSearch': 'درج در جستجو',
        'AccDescrRecordingTrimStart': 'برش از ابتدا',
        'AccDescrRecordingTrimEnd': 'برش از انتها',
        'AccDescrPaintColors': 'رنگ\u200cها',
        'AccDescrPaintColor': 'رنگ',
        'AccDescrPaintPen': 'قلم',
        'AccDescrPaintMarker': 'ماژیک',
        'AccDescrPaintNeon': 'نئون',
        'AccDescrPaintBlur': 'محو',
        'AccDescrPaintEraser': 'پاک\u200cکن',
        'AccDescrPaintShapes': 'شکل\u200cها',
        'AccDescrPaintSize': 'اندازه\u200cی قلم',
        'AccDescrTextAlignment': 'تراز متن',
        'AccDescrTextStyle': 'سبک متن',
        'AccDescrMediaDownloaded': 'دانلود شده',
        'AccDescrMediaNotDownloaded': 'دانلود نشده',
        'AccDescrTransferredSize': '%1$s از %2$s',
        'AccDescrDiceMissed': 'به هدف نخورد',
        'AccDescrDiceOnTarget': 'روی صفحه\u200cی هدف',
        'AccDescrDiceBullseye': 'وسط هدف',
        'AccDescrDiceScored': 'امتیاز گرفت',
        'AccDescrDiceGoal': 'گل',
        'AccDescrDiceStrike': 'استرایک',
        'AccDescrChatInFolders': 'در %s',
        'AccDescrMessageEffect': 'ارسال\u200cشده با %s',
        'AccDescrChatHiddenInCommunity': 'پنهان در کامیونیتی',
        'AccDescrChatUnreadStories': 'دارای استوری جدید',
        'AccDescrPollMultipleChoice': 'انتخاب بیش از یک گزینه',
        'AccDescrPollVoted': 'شما رأی داده\u200cاید',
        'AccDescrPollClosesAt': 'بسته می\u200cشود در %s',
        'AccDescrPollExplanationMedia': '%s مربوط به توضیح',
        'AccActionMoveUp': 'بردن به بالا',
        'AccActionMoveDown': 'بردن به پایین',
        'AccDescrPollOptionMoved': 'اکنون %1$d از %2$d',
        'AccDescrDownloadMoved': 'اکنون %1$d از %2$d',
        'AccDescrDownloadPaused': 'متوقف شده',
        'AccDescrPollOptionNumber': 'گزینه\u200cی %1$d از %2$d',
        'AccDescrTodoTaskNumber': 'کار %1$d از %2$d',
        'AccDescrPollCharactersLeft': '%s مانده',
        'AccDescrPollNoQuestion': 'اول یک سؤال بپرسید',
        'AccDescrPollNoOptions': 'اول یک گزینه اضافه کنید',
        'AccDescrPollQuestionTooLong': 'سؤال خیلی طولانی است',
        'AccDescrPollOptionTooLong': 'یکی از گزینه\u200cها خیلی طولانی است',
        'AccDescrPollDescriptionTooLong': 'توضیحات خیلی طولانی است',
        'AccDescrPollExplanationTooLong': 'توضیح پاسخ خیلی طولانی است',
        'AccDescrTodoNoTitle': 'اول برای چک\u200cلیست یک عنوان بگذارید',
        'AccDescrTodoNoTasks': 'اول یک کار اضافه کنید',
        'AccDescrTodoTitleTooLong': 'عنوان خیلی طولانی است',
        'AccDescrTodoTaskTooLong': 'یکی از کارها خیلی طولانی است',
        'AccDescrPollQuizLocked': 'این نظرسنجی به\u200cصورت آزمون شروع شده و همین\u200cطور می\u200cماند',
        'AccDescrPollAddingOptionsLocked': 'وقتی نظرسنجی آزمون است یا نشان می\u200cدهد چه کسی رأی داده، ممکن نیست',
        'AccDescrTodoDone': 'انجام شد',
        'AccDescrTodoDoneBy': 'انجام\u200cشده توسط %s',
        'AccDescrPollVotedBy': 'رأی\u200cداده توسط %s',
        'AccActionCopyText': 'کپی %s',
        'AccDescrChatMarkedUnread': 'به\u200cعنوان نخوانده علامت خورده',
        'AccDescrChatPinned': 'سنجاق\u200cشده',
        'AccDescrChatBotVerified': 'ربات تأییدشده',
        'AccDescrChatVoiceChatActive': 'ویس\u200cچت در جریان است',
        'AccDescrChatUnreadPollVotes': 'با رأی\u200cهای جدید نظرسنجی',
        'AccDescrNotificationsUnmuted': 'اعلان\u200cها روشن',
        'AccDescrCameraFront': 'دوربین جلو',
        'AccDescrCameraBack': 'دوربین عقب',
        'AccDescrDiceWin': 'برد',
        'AccDescrSlotBar': 'بار',
        'AccDescrSlotBerries': 'توت',
        'AccDescrSlotLemon': 'لیمو',
        'AccDescrSlotSeven': 'هفت',
        'AccDescrSlotJackpot': 'جکپات',
        'AccDescrCustomEmojiNamed': '%1$s، ایموجی سفارشی',
    }
    src = RES / "values/strings.xml"
    if not src.exists():
        return
    base = src.read_text(encoding="utf-8")
    n = 0
    for rel in ("values-fa/strings.xml", "values-fa-rIR/strings.xml"):
        path = RES / rel
        if not path.exists():
            continue
        for name, value in fa.items():
            if f'name="{name}"' not in base:
                continue  # the fork patch was not applied / key not present
            if f'name="{name}"' in path.read_text(encoding="utf-8"):
                continue
            esc = value.replace("&", "&amp;").replace("<", "&lt;").replace("'", "\\'")
            txt = path.read_text(encoding="utf-8")
            path.write_text(txt.replace("</resources>", f'    <string name="{name}">{esc}</string>\n</resources>'), encoding="utf-8")
            n += 1
    print("Persian strings for the fork's additions OK (%d written)" % n)

# ---- legacy versions, used only when the fork patch is NOT applied (plain upstream tree) ----
def patch_dialogcell_preview_muted_status_legacy() -> None:
    """
    Accessibility-fork additions to DialogCell.java's TalkBack description:
      - remove the "Muted" announcement entirely
      - read the contact's online/last-seen status (private chats only),
        gated by A11yConfig.getShowStatusInPreview()
      - bump the message-preview length read aloud from the visually
        truncated length to a fixed 300 characters
    """
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    if not dc.exists():
        print("WARN: DialogCell missing (preview/muted/status)")
        return
    t = dc.read_text(encoding="utf-8")
    if "a11y-fork: muted/status/preview-300" in t:
        print("DialogCell muted/status/preview-300 already patched")
        return

    old_block = (
        "        if (dialogMuted) {\n"
        "            sb.append(getString(R.string.AccDescrNotificationsMuted));\n"
        "            sb.append(\". \");\n"
        "        }\n"
        "        if (isOnline()) {\n"
        "            sb.append(getString(R.string.AccDescrUserOnline));\n"
        "            sb.append(\". \");\n"
        "        }\n"
    )
    new_block = (
        "        // a11y-fork: muted/status/preview-300 -- \"Muted\" removed,\n"
        "        // online/last-seen status announced instead when enabled.\n"
        "        if (user != null && org.telegram.messenger.A11yConfig.getShowStatusInPreview()) {\n"
        "            try {\n"
        "                String statusText = LocaleController.formatUserStatus(UserConfig.selectedAccount, user);\n"
        "                if (statusText != null && statusText.length() > 0) {\n"
        "                    sb.append(statusText);\n"
        "                    sb.append(\". \");\n"
        "                }\n"
        "            } catch (Throwable ignore) {\n"
        "            }\n"
        "        }\n"
    )
    if old_block not in t:
        print("WARN: DialogCell muted/status block not found")
        return
    t = t.replace(old_block, new_block)

    old_len = (
        "            int len = messageLayout == null ? -1 : messageLayout.getText().length();\n"
        "            if (len > 0) {"
    )
    new_len = (
        "            int len = 300; // a11y-fork: read up to 300 characters, not just the visually truncated amount\n"
        "            if (len > 0 && len < messageString.length()) {"
    )
    if old_len not in t:
        print("WARN: DialogCell preview-length block not found")
    else:
        t = t.replace(old_len, new_len)

    # Keep Telegram's native preview date/time block untouched.
    # Solar Hijri applies only to message-focus accessibility in ChatMessageCell.

    dc.write_text(t, encoding="utf-8")
    print("DialogCell muted removed / status announce / preview-300 / time-last OK")





def patch_dialogcell_time_last_legacy() -> None:
    """Move Telegram's native sent/received sentence to the absolute end of Preview.

    Do not build a separate accessibility field: Telegram's own StringBuilder is
    the content description used by both the AccessibilityEvent and the View.
    Removing the native block and inserting the exact same block immediately
    before those final calls guarantees TalkBack receives it as the last item.
    Preview deliberately stays Gregorian/native; Solar Hijri is for chat-message
    date separators only.
    """
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    if not dc.exists():
        print("WARN: DialogCell missing (time-last)")
        return
    t = dc.read_text(encoding="utf-8")
    marker = "a11y-fork: preview sent-received-last v5"
    if marker in t:
        print("DialogCell sent/received LAST v5 already patched")
        return

    # Remove any field-based v4 implementation from v16, if present.
    t = re.sub(
        r'(?m)^\s*// a11y-fork: preview sent-received field(?: v[0-9]+)?\n\s*private String a11yPreviewSentReceivedDate;\n',
        '', t, count=1
    )
    t = re.sub(
        r'(?m)^\s*// a11y-fork: preview sent-received-last[^\n]*\n'
        r'\s*if \(a11yPreviewSentReceivedDate != null && a11yPreviewSentReceivedDate\.length\(\) > 0\) \{\n'
        r'\s*sb\.append\(a11yPreviewSentReceivedDate\);\n'
        r'\s*sb\.append\("\. "\);\n\s*\}\n',
        '', t, count=1
    )

    # Remove the native early sent/received block, wherever it occurs.
    native = re.compile(
        r'(?m)^\s*String date = LocaleController\.formatDateAudio\(lastDate, true\);\n'
        r'\s*if \(message\.isOut\(\)\) \{\n'
        r'\s*sb\.append\(LocaleController\.formatString\("AccDescrSentDate", R\.string\.AccDescrSentDate, date\)\);\n'
        r'\s*\} else \{\n'
        r'\s*sb\.append\(LocaleController\.formatString\("AccDescrReceivedDate", R\.string\.AccDescrReceivedDate, date\)\);\n'
        r'\s*\}\n\s*sb\.append\("\. "\);\n'
    )
    m = native.search(t)
    if not m:
        print("WARN: DialogCell native sent/received date block not found (time-last)")
        return
    t = t[:m.start()] + t[m.end():]

    # Insert it immediately before the final accessibility-description calls.
    tail = (
        '        // ' + marker + '\n'
        '        String a11yPreviewDate = LocaleController.formatDateAudio(lastDate, true);\n'
        '        if (message.isOut()) {\n'
        '            sb.append(LocaleController.formatString("AccDescrSentDate", R.string.AccDescrSentDate, a11yPreviewDate));\n'
        '        } else {\n'
        '            sb.append(LocaleController.formatString("AccDescrReceivedDate", R.string.AccDescrReceivedDate, a11yPreviewDate));\n'
        '        }\n'
        '        sb.append(". ");\n'
    )
    final = re.search(r'(?m)^        event\.setContentDescription\(sb\);\n        setContentDescription\(sb\);', t)
    if not final:
        print("WARN: DialogCell final event/setContentDescription pair not found (time-last)")
        return
    t = t[:final.start()] + tail + t[final.start():]
    dc.write_text(t, encoding="utf-8")
    print("DialogCell sent/received LAST v5 OK")





def patch_chat_message_cell_granularity_navigation_legacy() -> None:
    """Implement real character/word TalkBack text-navigation for the message
    accessibility node. The base View class's performAccessibilityAction has no
    text-cursor concept for a non-TextView custom View, so ACTION_NEXT/PREVIOUS_
    AT_MOVEMENT_GRANULARITY were never handled -- TalkBack would fall through to
    unrelated "move to next accessibility element" behavior (observed as jumping
    to the toolbar's Search button) instead of stepping character-by-character
    or word-by-word through the message text. This adds the missing declaration
    (setMovementGranularities/addAction) plus the actual traversal logic.
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        print("WARN: ChatMessageCell missing (granularity navigation)")
        return
    t = cmc.read_text(encoding="utf-8")
    marker = "a11y-fork: granularity-navigation-v1"
    if marker in t:
        print("ChatMessageCell granularity navigation already patched")
        return

    field_anchor = "    CharSequence accessibilityText;"
    if field_anchor not in t:
        print("WARN: accessibilityText field anchor not found (granularity navigation)")
        return
    t = t.replace(field_anchor, field_anchor + "\n    private int a11yGranularityCursor = -1; // " + marker, 1)

    reset_anchor = "        accessibilityText = null;"
    if reset_anchor not in t:
        print("WARN: accessibilityText reset anchor not found (granularity navigation)")
        return
    t = t.replace(reset_anchor, reset_anchor + "\n        a11yGranularityCursor = -1;", 1)

    decl_anchor = (
        "                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {\n"
        "                    info.setContentDescription(accessibilityText.toString());\n"
        "                } else {\n"
        "                    info.setText(accessibilityText);\n"
        "                }\n"
    )
    if decl_anchor not in t:
        print("WARN: host info.setText anchor not found (granularity navigation)")
        return
    decl_new = (
        "                // " + marker + "\n"
        "                info.setMovementGranularities(AccessibilityNodeInfo.MOVEMENT_GRANULARITY_CHARACTER\n"
        "                        | AccessibilityNodeInfo.MOVEMENT_GRANULARITY_WORD);\n"
        "                info.addAction(AccessibilityNodeInfo.ACTION_NEXT_AT_MOVEMENT_GRANULARITY);\n"
        "                info.addAction(AccessibilityNodeInfo.ACTION_PREVIOUS_AT_MOVEMENT_GRANULARITY);\n"
        + decl_anchor
    )
    t = t.replace(decl_anchor, decl_new, 1)

    trav_anchor = "        return super.performAccessibilityAction(action, arguments);\n    }"
    if trav_anchor not in t:
        print("WARN: performAccessibilityAction fallthrough anchor not found (granularity navigation)")
        return
    trav_new = '        // a11y-fork: granularity-navigation-v1\n        if ((action == AccessibilityNodeInfo.ACTION_NEXT_AT_MOVEMENT_GRANULARITY\n                || action == AccessibilityNodeInfo.ACTION_PREVIOUS_AT_MOVEMENT_GRANULARITY)\n                && arguments != null && accessibilityText != null) {\n            try {\n                int a11yGranularity = arguments.getInt(AccessibilityNodeInfo.ACTION_ARGUMENT_MOVEMENT_GRANULARITY_INT);\n                boolean a11yForward = action == AccessibilityNodeInfo.ACTION_NEXT_AT_MOVEMENT_GRANULARITY;\n                String a11yFullText = accessibilityText.toString();\n                int a11yLen = a11yFullText.length();\n                int a11yCur = a11yGranularityCursor;\n                if (a11yCur < 0 || a11yCur > a11yLen) {\n                    a11yCur = a11yForward ? 0 : a11yLen;\n                }\n                int[] a11ySeg = null;\n                if (a11yGranularity == AccessibilityNodeInfo.MOVEMENT_GRANULARITY_CHARACTER) {\n                    if (a11yForward) {\n                        if (a11yCur < a11yLen) {\n                            int a11yNext = a11yCur + Character.charCount(a11yFullText.codePointAt(a11yCur));\n                            a11ySeg = new int[]{a11yCur, Math.min(a11yLen, a11yNext)};\n                        }\n                    } else {\n                        if (a11yCur > 0) {\n                            int a11yPrev = a11yCur - Character.charCount(a11yFullText.codePointBefore(a11yCur));\n                            a11ySeg = new int[]{Math.max(0, a11yPrev), a11yCur};\n                        }\n                    }\n                } else if (a11yGranularity == AccessibilityNodeInfo.MOVEMENT_GRANULARITY_WORD) {\n                    android.icu.text.BreakIterator a11yWordIt = android.icu.text.BreakIterator.getWordInstance();\n                    a11yWordIt.setText(a11yFullText);\n                    if (a11yForward) {\n                        int a11yStart = a11yWordIt.following(Math.max(0, Math.min(a11yLen - 1, a11yCur - 1)));\n                        while (a11yStart != android.icu.text.BreakIterator.DONE && a11yStart < a11yLen) {\n                            int a11yEnd = a11yWordIt.next();\n                            if (a11yEnd == android.icu.text.BreakIterator.DONE) break;\n                            if (Character.isLetterOrDigit(a11yFullText.codePointAt(a11yStart))) {\n                                a11ySeg = new int[]{a11yStart, a11yEnd};\n                                break;\n                            }\n                            a11yStart = a11yEnd;\n                        }\n                    } else {\n                        int a11yEnd = a11yWordIt.preceding(Math.max(0, Math.min(a11yLen, a11yCur)));\n                        while (a11yEnd != android.icu.text.BreakIterator.DONE && a11yEnd > 0) {\n                            int a11yStart = a11yWordIt.previous();\n                            if (a11yStart == android.icu.text.BreakIterator.DONE) break;\n                            if (a11yStart < a11yEnd && Character.isLetterOrDigit(a11yFullText.codePointAt(a11yStart))) {\n                                a11ySeg = new int[]{a11yStart, a11yEnd};\n                                break;\n                            }\n                            a11yEnd = a11yStart;\n                        }\n                    }\n                }\n                if (a11ySeg != null) {\n                    a11yGranularityCursor = a11yForward ? a11ySeg[1] : a11ySeg[0];\n                    AccessibilityEvent a11yTravEvent = AccessibilityEvent.obtain(AccessibilityEvent.TYPE_VIEW_TEXT_TRAVERSED_AT_MOVEMENT_GRANULARITY);\n                    a11yTravEvent.setPackageName(getContext().getPackageName());\n                    a11yTravEvent.setSource(ChatMessageCell.this, AccessibilityNodeProvider.HOST_VIEW_ID);\n                    a11yTravEvent.setFromIndex(a11ySeg[0]);\n                    a11yTravEvent.setToIndex(a11ySeg[1]);\n                    a11yTravEvent.setAction(action);\n                    a11yTravEvent.setMovementGranularity(a11yGranularity);\n                    a11yTravEvent.getText().add(a11yFullText);\n                    if (getParent() != null) {\n                        getParent().requestSendAccessibilityEvent(ChatMessageCell.this, a11yTravEvent);\n                    }\n                    return true;\n                }\n                return false;\n            } catch (Throwable a11yGranErr) {\n                FileLog.e(a11yGranErr);\n            }\n        }\n        return super.performAccessibilityAction(action, arguments);\n    }'
    t = t.replace(trav_anchor, trav_new, 1)

    cmc.write_text(t, encoding="utf-8")
    print("ChatMessageCell granularity navigation v1 OK")




def patch_reply_forward_long_click() -> None:
    """Long press on the reply / forward header of a message opened the REPLIED message.

    The header is its own accessibility node that advertised only CLICK. For a node without
    a long-click action TalkBack answers "double tap and hold" with a real touch held at the
    node's middle, and a held touch on the reply header is what Telegram itself turns into a
    jump to the replied message. The nodes now advertise LONG_CLICK, which the long-click
    patch routes to the Message Options menu (patch_chat_message_cell_accessibility_long_click).
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if not cmc.exists():
        print("WARN: ChatMessageCell missing (reply long-click)")
        return
    t = cmc.read_text(encoding="utf-8")
    marker = "// a11y-fork: reply-header long-click"
    if marker in t:
        print("ChatMessageCell reply/forward long-click already patched")
        return
    done = 0
    for node in ("REPLY", "FORWARD"):
        pat = re.compile(r"(virtualViewId == " + node + r"\) \{\n\s+info\.setEnabled\(true\);.*?info\.addAction\(AccessibilityNodeInfo\.ACTION_CLICK\);)", re.S)
        m = pat.search(t)
        if not m or "rect.set(" not in t[m.end():m.end() + 200]:
            print("WARN: %s node anchor not found (reply long-click)" % node)
            continue
        add = "\n                    info.addAction(AccessibilityNodeInfo.ACTION_LONG_CLICK); " + marker + " (" + node + ")"
        t = t[:m.end()] + add + t[m.end():]
        done += 1
    if done:
        cmc.write_text(t, encoding="utf-8")
        print("ChatMessageCell reply/forward header long-click OK (%d nodes)" % done)


def patch_fork_quiet_download_state() -> None:
    """The fork says "Downloaded" / "Not downloaded" on EVERY media message (photos, videos,
    files, voice, music ...) it passes, and on every row of a music list. That is noise, so it
    is controlled by the Accessible Settings option "Downloaded / not downloaded status"
    (A11yConfig.getAnnounceDownloadState(), default OFF).
    Not affected by that option: the fork's one-time "Downloaded" spoken when a download that
    was running reaches its end while the message is being read (right after the percentage
    reaches 100).
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if cmc.exists():
        t = cmc.read_text(encoding="utf-8")
        old = ("                if (hasAccessibilityDownloadState()) {\n"
               "                    sb.append(\", \");\n"
               "                    sb.append(getString(mediaDownloaded ? R.string.AccDescrMediaDownloaded : R.string.AccDescrMediaNotDownloaded));\n"
               "                }\n")
        pat = re.compile(r"(\n[ \t]*)if \(hasAccessibilityDownloadState\(\)\) \{(\n[ \t]*sb\.append\(\", \"\);\n[ \t]*sb\.append\(getString\(mediaDownloaded \? R\.string\.AccDescrMediaDownloaded : R\.string\.AccDescrMediaNotDownloaded\)\);\n[ \t]*\})")
        if "A11yConfig.getAnnounceDownloadState()" in t:
            print("ChatMessageCell download-state setting already patched")
        elif pat.search(t):
            t = pat.sub(lambda m: m.group(1) + "if (hasAccessibilityDownloadState() && org.telegram.messenger.A11yConfig.getAnnounceDownloadState()) { // a11y-fork: setting" + m.group(2), t, count=1)
            cmc.write_text(t, encoding="utf-8")
            print("ChatMessageCell download-state setting OK")
        else:
            print("WARN: ChatMessageCell permanent download-state block not found")
    sac = JAVA / "org/telegram/ui/Cells/SharedAudioCell.java"
    if sac.exists():
        t = sac.read_text(encoding="utf-8")
        old = "    public static void appendAccessibilityDownloadState(AccessibilityNodeInfo info, boolean downloaded, boolean downloading, String fileName) {\n"
        if "A11yConfig.getAnnounceDownloadState()" in t:
            print("SharedAudioCell download-state setting already patched")
        elif old in t:
            t = t.replace(old, old + "        // a11y-fork: setting -- only when \"Downloaded / not downloaded status\" is ON, and then only the\n"
                                      "        // state words (no percentage: progress is announced by our own RadialProgress)\n"
                                      "        if (!org.telegram.messenger.A11yConfig.getAnnounceDownloadState() || downloading) {\n"
                                      "            return;\n"
                                      "        }\n", 1)
            sac.write_text(t, encoding="utf-8")
            print("SharedAudioCell download-state setting OK")
        else:
            print("WARN: SharedAudioCell appendAccessibilityDownloadState not found")


def _gate_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace `old` by `new` exactly once in `path`; print OK / already / WARN."""
    if not path.exists():
        print("WARN: %s missing (%s)" % (path.name, label))
        return
    t = path.read_text(encoding="utf-8")
    if new in t:
        print("%s already patched" % label)
        return
    if t.count(old) != 1:
        print("WARN: %s anchor found %d times in %s" % (label, t.count(old), path.name))
        return
    path.write_text(t.replace(old, new, 1), encoding="utf-8")
    print("%s OK" % label)


def patch_album_and_user_status_switches() -> None:
    """Two Accessible Settings switches, both default OFF, for features the fork turns on always.

      * "Album reading" (A11yConfig.getAlbumReading): the fork says "Album, photo 2 of 5" for every
        message of a grouped-media album. OFF = the message is read like any other (stock Telegram).
      * "User status announcements" (A11yConfig.getUserStatusAnnounce): the fork speaks what a
        contact is doing -- typing, recording a voice message, sending audio, online -- in the chat
        header, in the chat list while a row is focused, and inside the row's own description.
        OFF = none of it is spoken (stock Telegram).
    """
    A = "org.telegram.messenger.A11yConfig"
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    _gate_once(
        cmc,
        "    private CharSequence albumAccessibilityPlace() {\n"
        "        if (currentMessageObject == null || currentMessagesGroup == null || currentPosition == null) {\n",
        "    private CharSequence albumAccessibilityPlace() {\n"
        "        if (!" + A + ".getAlbumReading()) { // a11y-fork: setting (default OFF = stock wording)\n"
        "            return null;\n"
        "        }\n"
        "        if (currentMessageObject == null || currentMessagesGroup == null || currentPosition == null) {\n",
        "ChatMessageCell album-reading switch")
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    _gate_once(
        dc,
        "        final CharSequence print = MessagesController.getInstance(currentAccount).getPrintingString(currentDialogId, getTopicId(), true);\n",
        "        final CharSequence print = !" + A + ".getUserStatusAnnounce() ? null : MessagesController.getInstance(currentAccount).getPrintingString(currentDialogId, getTopicId(), true); // a11y-fork: setting\n",
        "DialogCell live typing/recording switch")
    _gate_once(
        dc,
        "            if (online && !accessibilityStateOnline) {\n",
        "            if (online && !accessibilityStateOnline && " + A + ".getUserStatusAnnounce()) { // a11y-fork: setting\n",
        "DialogCell live online switch")
    _gate_once(
        dc,
        "        final CharSequence typing = printingStringType >= 0 && typingLayout != null ? typingLayout.getText() : null;\n",
        "        final CharSequence typing = " + A + ".getUserStatusAnnounce() && printingStringType >= 0 && typingLayout != null ? typingLayout.getText() : null; // a11y-fork: setting\n",
        "DialogCell row-description typing switch")
    cac = JAVA / "org/telegram/ui/Components/ChatAvatarContainer.java"
    _gate_once(
        cac,
        "    private void announceSubtitleChange(CharSequence newSubtitle) {\n",
        "    private void announceSubtitleChange(CharSequence newSubtitle) {\n"
        "        if (!" + A + ".getUserStatusAnnounce()) { // a11y-fork: setting (default OFF = nothing spoken)\n"
        "            return;\n"
        "        }\n",
        "ChatAvatarContainer header status switch")


def patch_chat_open_sound() -> None:
    """Optional system click (the phone's "Touch sounds") the moment the chat fragment opens.

    It is played from ChatActivity.onTransitionAnimationStart(isOpen = true, backward = false),
    i.e. right when the tap on the chat list is handled -- exactly like a normal touch -- and NOT
    when messages finish loading and TalkBack's focus lands on one of them. Once per fragment
    instance; chat previews and chats embedded inside another screen stay silent.
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    old = (
        "    public void onTransitionAnimationStart(boolean isOpen, boolean backward) {\n"
        "        super.onTransitionAnimationStart(isOpen, backward);\n")
    new = (old +
           "        if (isOpen && !backward && !a11yChatOpenSoundPlayed && !isInPreviewMode() && !isInsideContainer) { // a11y-fork: chat-open sound\n"
           "            a11yChatOpenSoundPlayed = true;\n"
           "            org.telegram.messenger.A11yConfig.playChatOpenSoundUnlessJustTapped();\n"
           "        }\n")
    field_anchor = "    long startMs;\n    @Override\n    public void onTransitionAnimationStart(boolean isOpen, boolean backward) {\n"
    if not ca.exists():
        print("WARN: ChatActivity.java missing (chat-open sound)")
        return
    t = ca.read_text(encoding="utf-8")
    if "a11yChatOpenSoundPlayed" in t:
        print("ChatActivity chat-open sound already patched")
        return
    if t.count(old) != 1 or t.count(field_anchor) != 1:
        print("WARN: ChatActivity chat-open sound anchor not found (%d/%d)" % (t.count(old), t.count(field_anchor)))
        return
    t = t.replace(field_anchor, "    private boolean a11yChatOpenSoundPlayed; // a11y-fork: chat-open sound, once per fragment\n" + field_anchor, 1)
    t = t.replace(old, new, 1)
    # the fork's old trigger (sound when TalkBack focus lands on a message) must not fire a second click
    old_fork = ("            if (landed && !requested) { // a11y-fork: optional chat-open sound (setting, default OFF)\n"
                "                org.telegram.messenger.A11yConfig.playChatOpenSound();\n"
                "            }\n")
    if old_fork in t:
        t = t.replace(old_fork, "", 1)
        print("removed old focus-landing chat-open sound")
    ca.write_text(t, encoding="utf-8")
    print("ChatActivity chat-open sound (fragment open) OK")


def patch_unlabeled_buttons() -> None:
    """Give buttons that TalkBack announces as "unlabeled" a real name (English + Persian).

      * Video player (PhotoViewer): the button beside "More options" that opens the video
        quality / speed / loop menu (videoItem) had no content description at all.
      * Add members (GroupCreateActivity): the round check button that confirms the selected
        people was named "Next" (copied from the new-group flow where it really is a next arrow).
        In add-to-group / always-share / never-share mode it is a confirm button, so it is named
        for what it does.
    """
    pv = JAVA / "org/telegram/ui/PhotoViewer.java"
    _gate_once(
        pv,
        "        videoItemIcon.setCallback(videoItem.getIconView());\n",
        "        videoItem.setContentDescription(LocaleController.getString(R.string.A11yVideoSettings)); // a11y-fork: label\n"
        "        videoItemIcon.setCallback(videoItem.getIconView());\n",
        "PhotoViewer video settings button label")
    gca = JAVA / "org/telegram/ui/GroupCreateActivity.java"
    _gate_once(
        gca,
        "        floatingButton.setContentDescription(getString(R.string.Next));\n",
        "        floatingButton.setContentDescription((isNeverShare || isAlwaysShare || addToGroup) ? getString(R.string.A11yAddMembersConfirm) : getString(R.string.Next)); // a11y-fork: label\n",
        "GroupCreateActivity confirm button label")


def patch_audit_unlabeled_buttons() -> None:
    """Buttons found with no name by reading the Telegram source (not reported by hand).

    A scan of the whole source for (a) round / icon buttons that have a click listener but no content
    description and (b) icon-only toolbar items without one, then reading each hit, left these:

      * Business links (BusinessLinksActivity): the round link button of a link's row copies the
        link and was read as "unlabeled" -> "Copy link".
      * Channel / group colour and wallpaper pages (ChannelColorActivity, ChannelWallpaperActivity):
        the sun / moon button of the toolbar switches the preview between the day and night theme
        and had no name. It is named for what a press does, asked each time (the very strings the
        profile colour page already uses), because the theme can change while the page is open.

    Everything else the scan listed was already named some other way (the name is set in
    onInitializeAccessibilityNodeInfo, by setSearchFieldHint, further down the file), was a picture
    inside a row, or sits in commented-out code, so it is left alone.
    """
    bl = JAVA / "org/telegram/ui/Business/BusinessLinksActivity.java"
    _gate_once(
        bl,
        "            imageView.setBackground(Theme.createCircleDrawable(dp(36), Theme.getColor(Theme.key_featuredStickers_addButton)));\n"
        "            imageView.setOnClickListener(view -> {\n"
        "                if (businessLink != null) {\n",
        "            imageView.setBackground(Theme.createCircleDrawable(dp(36), Theme.getColor(Theme.key_featuredStickers_addButton)));\n"
        "            imageView.setContentDescription(LocaleController.getString(R.string.CopyLink)); // a11y-fork: label\n"
        "            imageView.setOnClickListener(view -> {\n"
        "                if (businessLink != null) {\n",
        "BusinessLinksActivity copy link button label")
    delegate_tpl = (
        "{indent}dayNightItem.setAccessibilityDelegate(new android.view.View.AccessibilityDelegate() {{ // a11y-fork: label\n"
        "{indent}    @Override\n"
        "{indent}    public void onInitializeAccessibilityNodeInfo(android.view.View host, android.view.accessibility.AccessibilityNodeInfo info) {{\n"
        "{indent}        super.onInitializeAccessibilityNodeInfo(host, info);\n"
        "{indent}        info.setContentDescription(LocaleController.getString({dark} ? R.string.AccDescrSwitchToDayTheme : R.string.AccDescrSwitchToNightTheme));\n"
        "{indent}    }}\n"
        "{indent}}});\n")
    cc = JAVA / "org/telegram/ui/ChannelColorActivity.java"
    a = "        dayNightItem = actionBar.createMenu().addItem(1, sunDrawable);\n"
    _gate_once(cc, a, a + delegate_tpl.format(indent="        ", dark="isDark"),
               "ChannelColorActivity day/night button label")
    cw = JAVA / "org/telegram/ui/ChannelWallpaperActivity.java"
    b = "            dayNightItem = actionBar.createMenu().addItem(1, sunDrawable);\n"
    _gate_once(cw, b, b + delegate_tpl.format(indent="            ", dark="isDark()"),
               "ChannelWallpaperActivity day/night button label")


def patch_contacts_list_accessibility() -> None:
    """Contacts list (New message / Contacts): two fixes in UserCell, switched on only by ContactsAdapter.

      * "Not checked" is spoken on every contact even though nothing is being selected. The state
        is now spoken only once a selection has started (something is selected), and then on every
        contact, as asked.
      * A contact who has you as a contact too is read as "Mutual contact" (User.mutual_contact).
    """
    uc = JAVA / "org/telegram/ui/Cells/UserCell.java"
    _gate_once(
        uc,
        "    @Override\n    public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {\n"
        "        super.onInitializeAccessibilityNodeInfo(info);\n"
        "        if (checkBoxBig != null && checkBoxBig.getVisibility() == VISIBLE) {\n"
        "            info.setCheckable(true);\n"
        "            info.setChecked(checkBoxBig.isChecked());\n"
        "            info.setClassName(\"android.widget.CheckBox\");\n"
        "        } else if (checkBox != null && checkBox.getVisibility() == VISIBLE) {\n"
        "            info.setCheckable(true);\n"
        "            info.setChecked(checkBox.isChecked());\n"
        "            info.setClassName(\"android.widget.CheckBox\");\n"
        "        }\n",
        "    // a11y-fork: contacts list switches (set by ContactsAdapter only)\n"
        "    public interface A11ySelectionMode {\n"
        "        boolean isActive();\n"
        "    }\n"
        "    public A11ySelectionMode a11ySelectionMode;\n"
        "    public boolean a11yAnnounceMutual;\n\n"
        "    @Override\n    public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {\n"
        "        super.onInitializeAccessibilityNodeInfo(info);\n"
        "        final boolean selecting = a11ySelectionMode == null || a11ySelectionMode.isActive();\n"
        "        if (checkBoxBig != null && checkBoxBig.getVisibility() == VISIBLE) {\n"
        "            if (selecting || checkBoxBig.isChecked()) {\n"
        "                info.setCheckable(true);\n"
        "                info.setChecked(checkBoxBig.isChecked());\n"
        "                info.setClassName(\"android.widget.CheckBox\");\n"
        "            }\n"
        "        } else if (checkBox != null && checkBox.getVisibility() == VISIBLE) {\n"
        "            if (selecting || checkBox.isChecked()) {\n"
        "                info.setCheckable(true);\n"
        "                info.setChecked(checkBox.isChecked());\n"
        "                info.setClassName(\"android.widget.CheckBox\");\n"
        "            }\n"
        "        }\n",
        "UserCell checkbox state only while selecting")
    _gate_once(
        uc,
        "        if (adminTextView != null && adminTextView.getVisibility() == VISIBLE) {\n"
        "            CharSequence admin = adminTextView.getText();\n",
        "        if (a11yAnnounceMutual && currentObject instanceof TLRPC.User && ((TLRPC.User) currentObject).mutual_contact) {\n"
        "            if (sb.length() > 0) sb.append(\", \");\n"
        "            sb.append(LocaleController.getString(R.string.A11yMutualContact)); // a11y-fork\n"
        "        }\n"
        "        if (adminTextView != null && adminTextView.getVisibility() == VISIBLE) {\n"
        "            CharSequence admin = adminTextView.getText();\n",
        "UserCell mutual contact")
    ca = JAVA / "org/telegram/ui/Adapters/ContactsAdapter.java"
    _gate_once(
        ca,
        "                UserCell cell = new UserCell(mContext, 58, 1, false);\n                cell.setCallCellStyle(58);\n",
        "                UserCell cell = new UserCell(mContext, 58, 1, false);\n"
        "                cell.a11ySelectionMode = () -> selectedContacts != null && selectedContacts.size() > 0; // a11y-fork\n"
        "                cell.a11yAnnounceMutual = true; // a11y-fork\n"
        "                cell.setCallCellStyle(58);\n",
        "ContactsAdapter contact cell switches")


def patch_topics_hide_chat_list_from_screen_reader() -> None:
    """Topics of a forum group open in a panel (RightSlidingDialogContainer) on top of the chat
    list, which stays on the screen underneath. A screen reader therefore walks through the whole
    chat list before / between the topics. While the panel is fully open every other child of its
    parent is hidden from accessibility (their previous setting is remembered and put back when the
    panel is closing or gone)."""
    rc = JAVA / "org/telegram/ui/RightSlidingDialogContainer.java"
    _gate_once(
        rc,
        "    protected void updateOpenAnimationProgress() {\n        if (replaceAnimationInProgress || !hasFragment()) {\n            return;\n        }\n",
        "    // a11y-fork: hide what is underneath from a screen reader while the panel is open\n"
        "    private final java.util.WeakHashMap<View, Integer> a11ySiblingModes = new java.util.WeakHashMap<>();\n"
        "    private boolean a11ySiblingsHidden;\n\n"
        "    private void a11yUpdateSiblings(boolean hide) {\n"
        "        if (hide == a11ySiblingsHidden) {\n"
        "            return;\n"
        "        }\n"
        "        a11ySiblingsHidden = hide;\n"
        "        if (!(getParent() instanceof android.view.ViewGroup)) {\n"
        "            return;\n"
        "        }\n"
        "        android.view.ViewGroup parent = (android.view.ViewGroup) getParent();\n"
        "        if (hide) {\n"
        "            a11ySiblingModes.clear();\n"
        "            for (int i = 0; i < parent.getChildCount(); i++) {\n"
        "                View child = parent.getChildAt(i);\n"
        "                if (child == this) {\n"
        "                    continue;\n"
        "                }\n"
        "                a11ySiblingModes.put(child, child.getImportantForAccessibility());\n"
        "                child.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);\n"
        "            }\n"
        "        } else {\n"
        "            for (java.util.Map.Entry<View, Integer> e : a11ySiblingModes.entrySet()) {\n"
        "                if (e.getKey() != null) {\n"
        "                    e.getKey().setImportantForAccessibility(e.getValue());\n"
        "                }\n"
        "            }\n"
        "            a11ySiblingModes.clear();\n"
        "        }\n"
        "    }\n\n"
        "    protected void updateOpenAnimationProgress() {\n"
        "        a11yUpdateSiblings(hasFragment() && isOpenned && openedProgress >= 0.99f);\n"
        "        if (replaceAnimationInProgress || !hasFragment()) {\n            return;\n        }\n",
        "RightSlidingDialogContainer hides chat list from screen reader")


def patch_more_unlabeled_buttons() -> None:
    """Second sweep for buttons TalkBack reads as "unlabeled" (found by scanning the whole UI source).

      * Voice chat banner (FragmentContextView): the round mute / unmute button -> "Mute" / "Unmute",
        kept in step with the microphone state.
      * Chat list (DialogsActivity): the avatar button that switches between accounts -> "Switch account".
      * Mini apps (BotWebViewSheet) and Select gifts: the "..." button -> "More options".
      * Chat background preview (ThemePreviewActivity): the sun / moon button -> "Switch to night /
        day theme", kept in step with the theme.
    Strings other than "Switch account" are the app's own, so they follow the app's language.
    """
    fcv = JAVA / "org/telegram/ui/Components/FragmentContextView.java"
    _gate_once(
        fcv,
        "            muteDrawable.setCurrentFrame(muteDrawable.getCustomEndFrame() - 1, false, true);\n"
        "            muteButton.invalidate();\n"
        "            frameLayout.setBackground(null);\n",
        "            muteDrawable.setCurrentFrame(muteDrawable.getCustomEndFrame() - 1, false, true);\n"
        "            muteButton.invalidate();\n"
        "            muteButton.setContentDescription(getString(isMuted ? R.string.VoipGroupUnmuteShort : R.string.VoipMute)); // a11y-fork: label\n"
        "            frameLayout.setBackground(null);\n",
        "FragmentContextView mute button label (start)")
    _gate_once(
        fcv,
        "                muteDrawable.setCurrentFrame(muteDrawable.getCustomEndFrame() - 1, false, true);\n"
        "                muteButton.invalidate();\n"
        "            }\n"
        "        } else if (currentStyle == STYLE_INACTIVE_GROUP_CALL) {\n",
        "                muteDrawable.setCurrentFrame(muteDrawable.getCustomEndFrame() - 1, false, true);\n"
        "                muteButton.invalidate();\n"
        "                muteButton.setContentDescription(getString(isMuted ? R.string.VoipGroupUnmuteShort : R.string.VoipMute)); // a11y-fork: label\n"
        "            }\n"
        "        } else if (currentStyle == STYLE_INACTIVE_GROUP_CALL) {\n",
        "FragmentContextView mute button label (update)")
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "            switchItem = menu.addItemWithWidth(11, 0, dp(56));\n",
        "            switchItem = menu.addItemWithWidth(11, 0, dp(56));\n"
        "            switchItem.setContentDescription(LocaleController.getString(R.string.A11ySwitchAccount)); // a11y-fork: label\n",
        "DialogsActivity switch account button label")
    bw = JAVA / "org/telegram/ui/bots/BotWebViewSheet.java"
    _gate_once(
        bw,
        "        optionsItem = menu.addItem(0, optionsIcon = new BotFullscreenButtons.OptionsIcon(getContext()));\n",
        "        optionsItem = menu.addItem(0, optionsIcon = new BotFullscreenButtons.OptionsIcon(getContext()));\n"
        "        optionsItem.setContentDescription(LocaleController.getString(R.string.AccDescrMoreOptions)); // a11y-fork: label\n",
        "BotWebViewSheet options button label")
    sg = JAVA / "org/telegram/ui/Gifts/SelectGiftsBottomSheet.java"
    _gate_once(
        sg,
        "        final ActionBarMenuItem other = menu.addItem(1, R.drawable.ic_ab_other);\n",
        "        final ActionBarMenuItem other = menu.addItem(1, R.drawable.ic_ab_other);\n"
        "        other.setContentDescription(org.telegram.messenger.LocaleController.getString(R.string.AccDescrMoreOptions)); // a11y-fork: label\n",
        "SelectGiftsBottomSheet more-options button label")
    tp = JAVA / "org/telegram/ui/ThemePreviewActivity.java"
    _gate_once(
        tp,
        "                    dayNightItem = menu2.addItem(OPTION_DAY_NIGHT, sunDrawable);\n",
        "                    dayNightItem = menu2.addItem(OPTION_DAY_NIGHT, sunDrawable);\n"
        "                    dayNightItem.setContentDescription(LocaleController.getString(onSwitchDayNightDelegate != null && onSwitchDayNightDelegate.isDark() ? R.string.AccDescrSwitchToDayTheme : R.string.AccDescrSwitchToNightTheme)); // a11y-fork: label\n",
        "ThemePreviewActivity day/night button label")
    _gate_once(
        tp,
        "                    boolean isDark = onSwitchDayNightDelegate.isDark();\n"
        "                    if (onSwitchDayNightDelegate != null) {\n",
        "                    boolean isDark = onSwitchDayNightDelegate.isDark();\n"
        "                    if (dayNightItem != null) { // a11y-fork: label now describes the next switch\n"
        "                        dayNightItem.setContentDescription(LocaleController.getString(isDark ? R.string.AccDescrSwitchToNightTheme : R.string.AccDescrSwitchToDayTheme));\n"
        "                    }\n"
        "                    if (onSwitchDayNightDelegate != null) {\n",
        "ThemePreviewActivity day/night button label (toggle)")


def patch_reply_longpress_opens_options() -> None:
    """A real long press on the reply header of a message (touch path: ChatMessageCell.onLongPress ->
    delegate.didPressReplyMessage(..., longpress=true)) is answered by stock ChatActivity like a short tap:
    it scrolls to the replied message. Here a long press there opens Message options, like a long press
    anywhere else on the message (the TalkBack action path already did)."""
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    _gate_once(
        ca,
        "            if (UserObject.isReplyUser(currentUser)) {\n"
        "                didPressSideButton(cell);\n"
        "                return;\n"
        "            }\n"
        "            MessageObject messageObject = cell.getMessageObject();\n"
        "            if (messageObject == null) return;\n"
        "            if (messageObject.isReplyToStory() && messageObject.messageOwner.replyStory != null) {\n",
        "            if (longpress && cell != null && cell.getMessageObject() != null && canPerformActions()) { // a11y-fork: reply long-press = Message options\n"
        "                didLongPress(cell, x, y);\n"
        "                return;\n"
        "            }\n"
        "            if (UserObject.isReplyUser(currentUser)) {\n"
        "                didPressSideButton(cell);\n"
        "                return;\n"
        "            }\n"
        "            MessageObject messageObject = cell.getMessageObject();\n"
        "            if (messageObject == null) return;\n"
        "            if (messageObject.isReplyToStory() && messageObject.messageOwner.replyStory != null) {\n",
        "ChatActivity reply long-press opens Message options")


def patch_longclickable_flag() -> None:
    """TalkBack plays its "long press" sound by looking at the node's long-clickable flag. A message
    node (and each of its virtual parts) answered ACTION_LONG_CLICK but never said "long-clickable",
    which is the likely reason the sound is missing on some messages such as grouped media.
    Declaring it changes nothing else: the action itself is already handled."""
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    _gate_once(
        cmc,
        "                info.setEnabled(true);\n"
        "                AccessibilityNodeInfo.CollectionItemInfo itemInfo = info.getCollectionItemInfo();\n",
        "                info.setEnabled(true);\n"
        "                info.setLongClickable(true); // a11y-fork: TalkBack long-press sound\n"
        "                AccessibilityNodeInfo.CollectionItemInfo itemInfo = info.getCollectionItemInfo();\n",
        "ChatMessageCell host node long-clickable flag")
    _gate_once(
        cmc,
        "                    if (!a11yHasLong) {\n"
        "                        a11yInfo.addAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);\n"
        "                    }\n",
        "                    if (!a11yHasLong) {\n"
        "                        a11yInfo.addAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);\n"
        "                    }\n"
        "                    a11yInfo.setLongClickable(true); // a11y-fork: TalkBack long-press sound\n",
        "ChatMessageCell virtual nodes long-clickable flag")


def _java_remove_method(text: str, signature: str) -> str:
    """Remove one Java method (brace matched) that starts with `signature`."""
    a = text.find(signature)
    if a < 0:
        return text
    i = text.index("{", a)
    depth = 0
    j = i
    while j < len(text):
        ch = text[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    # also swallow the line break(s) that followed the method
    while j < len(text) and text[j] in "\r\n":
        j += 1
    return text[:a] + text[j:]


def patch_a11y_settings_dialog_stays_open() -> None:
    """Accessible Settings stays open while options are changed.

    Before, every item click dismissed the dialog (AlertDialog.setItems), so a change dropped
    the user back on Telegram's Settings page. Now the list is a normal list whose rows are
    refreshed in place; the pickers (progress step, voice quality, small files) close only
    themselves; the dialog is left with its Close button / the back key.
    Also adds the "Downloaded / not downloaded status" setting (default OFF).
    """
    cfgp = JAVA / "org/telegram/messenger/A11yConfig.java"
    if not cfgp.exists():
        print("WARN: A11yConfig.java missing (settings dialog)")
        return
    t = cfgp.read_text(encoding="utf-8")
    marker = "a11y-fork: settings dialog stays open v1"
    if marker in t:
        print("A11yConfig settings dialog already patched")
        return
    for sig in ("    private static void showSmallFilesModePicker(",
                "    public static void showSettingsDialog(",
                "    private static void showProgressStepPicker(",
                "    private static void showVoiceQualityPicker("):
        if sig not in t:
            print("WARN: A11yConfig method not found: " + sig.strip())
            return
        t = _java_remove_method(t, sig)
    new_code = r"""
    // """ + marker + r"""
    public static final String PREF_DOWNLOAD_STATE = "a11y_download_state";

    /** Say "Downloaded" / "Not downloaded" on every media message and music row. Default OFF. */
    public static boolean getAnnounceDownloadState() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_DOWNLOAD_STATE, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setAnnounceDownloadState(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_DOWNLOAD_STATE, value).apply();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_ALBUM_READING = "a11y_album_reading";
    public static final String PREF_ADMIN_TAG = "a11y_admin_tag_announce";
    public static final String PREF_USER_STATUS = "a11y_user_status_announce";

    /** Read grouped messages (albums) as "Album, photo 2 of 5" like the fork does. Default OFF = stock Telegram wording. */
    public static boolean getAlbumReading() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_ALBUM_READING, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setAlbumReading(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_ALBUM_READING, value).apply();
        } catch (Throwable ignore) {
        }
    }

    /** Say the admin / owner / group-own tag after the sender name in groups. Default OFF. */
    public static boolean getAdminTagAnnounce() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_ADMIN_TAG, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setAdminTagAnnounce(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_ADMIN_TAG, value).apply();
        } catch (Throwable ignore) {
        }
    }

    /** Speak what a contact is doing (typing, recording a voice message, sending audio, online). Default OFF. */
    public static boolean getUserStatusAnnounce() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_USER_STATUS, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setUserStatusAnnounce(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_USER_STATUS, value).apply();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_CHAT_OPEN_SOUND = "a11y_chat_open_sound";

    /** Play the phone's own "Touch sounds" click once when a chat opens and focus lands on its message. Default OFF. */
    public static boolean getChatOpenSound() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_CHAT_OPEN_SOUND, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setChatOpenSound(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_CHAT_OPEN_SOUND, value).apply();
        } catch (Throwable ignore) {
        }
    }

    /** The system click ("Touch sounds" in the phone's Sound settings); the system itself stays silent when that is off. */
    public static void playChatOpenSound() {
        try {
            if (!getChatOpenSound()) {
                return;
            }
            android.media.AudioManager am = (android.media.AudioManager) ApplicationLoader.applicationContext.getSystemService(android.content.Context.AUDIO_SERVICE);
            if (am != null) {
                am.playSoundEffect(android.media.AudioManager.FX_KEY_CLICK);
            }
        } catch (Throwable ignore) {
        }
    }

    private static long lastRowTapSoundMs = -100000;

    /** The click for a tap on a chat row of a list: played at the tap itself, before the chat starts to open. */
    public static void playRowTapSound() {
        try {
            if (!getChatOpenSound()) {
                return;
            }
            lastRowTapSoundMs = android.os.SystemClock.elapsedRealtime();
            playChatOpenSound();
        } catch (Throwable ignore) {
        }
    }

    /**
     * The click for a chat that has just opened. A chat opened by a tap on its row has already
     * clicked at the tap (playRowTapSound), so it stays quiet; a chat opened any other way
     * (a notification, a link, a shortcut) still clicks, as it opens.
     */
    public static void playChatOpenSoundUnlessJustTapped() {
        try {
            if (android.os.SystemClock.elapsedRealtime() - lastRowTapSoundMs < 3000) {
                return;
            }
            playChatOpenSound();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_SENDER_OPTIONS = "a11y_sender_options_menu";

    /** Put the sender options (profile, private chat, mention, search their messages) in Message options. Default OFF. */
    public static boolean getSenderOptionsInMenu() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_SENDER_OPTIONS, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setSenderOptionsInMenu(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_SENDER_OPTIONS, value).apply();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_VOICE_SHARE_SAVE = "a11y_voice_share_save";
    public static final String PREF_PLAYER_SEEK = "a11y_player_seek_buttons";

    /** Share + Save to music in the menu of a downloaded voice message. Default OFF. */
    public static boolean getVoiceShareSave() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_VOICE_SHARE_SAVE, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setVoiceShareSave(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_VOICE_SHARE_SAVE, value).apply();
        } catch (Throwable ignore) {
        }
    }

    /** Rewind / Forward 10 s beside Close in the audio player bar. Default OFF. */
    public static boolean getPlayerSeekButtons() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_PLAYER_SEEK, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setPlayerSeekButtons(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_PLAYER_SEEK, value).apply();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_PROXY_TOOLBAR = "a11y_proxy_toolbar_button";

    /** Proxy button in the chat list's top bar, as older versions had it. Default OFF. */
    public static boolean getProxyButtonInToolbar() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_PROXY_TOOLBAR, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setProxyButtonInToolbar(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_PROXY_TOOLBAR, value).apply();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_OLD_MENU = "a11y_old_style_menu";

    /** Old-style main menu button (the old side drawer's entries) in the chat list's top bar. Default OFF. */
    public static boolean getOldStyleMenu() {
        return getMenuStyle() >= 1; // popup menu (1) or classic drawer (2): both replace the bottom tabs
    }

    public static void setOldStyleMenu(boolean value) {
        setMenuStyle(value ? 1 : 0);
    }

    public static final String PREF_MENU_STYLE = "a11y_menu_style";

    /** Main menu style: 0 = current Telegram (bottom tabs), 1 = old-style popup menu, 2 = classic navigation drawer. */
    public static int getMenuStyle() {
        try {
            android.content.SharedPreferences sp = MessagesController.getGlobalMainSettings();
            if (sp.contains(PREF_MENU_STYLE)) {
                int v = sp.getInt(PREF_MENU_STYLE, 0);
                return v < 0 || v > 2 ? 0 : v;
            }
            if (sp.getBoolean(PREF_LEGACY_DRAWER, false)) {
                return 2;
            }
            return sp.getBoolean(PREF_OLD_MENU, false) ? 1 : 0;
        } catch (Throwable ignore) {
            return 0;
        }
    }

    public static void setMenuStyle(int value) {
        try {
            MessagesController.getGlobalMainSettings().edit()
                    .putInt(PREF_MENU_STYLE, value)
                    .putBoolean(PREF_OLD_MENU, value >= 1)
                    .putBoolean(PREF_LEGACY_DRAWER, value == 2)
                    .apply();
        } catch (Throwable ignore) {
        }
    }

    private static String[] menuStyleLabels() {
        return new String[]{
                LocaleController.getString(R.string.A11yMenuStyleCurrent),
                LocaleController.getString(R.string.A11yMenuStyleOld),
                LocaleController.getString(R.string.A11yMenuStyleDrawer)
        };
    }

    private static void showMenuStylePicker(final Activity activity, final Runnable onChanged) {
        final String[] labels = menuStyleLabels();
        final int before = getMenuStyle();
        new AlertDialog.Builder(activity)
                .setTitle(LocaleController.getString(R.string.A11yMenuStylePickerTitle))
                .setSingleChoiceItems(labels, before, (d, which) -> {
                    setMenuStyle(which);
                    d.dismiss();
                    try {
                        org.telegram.ui.MainTabsActivity.a11yRefreshTabs();
                        org.telegram.ui.DialogsActivity.a11yRefreshCategory();
                    } catch (Throwable ignore) {
                    }
                    if (onChanged != null) onChanged.run();
                    String msg = labels[which];
                    if ((which == 2) != (before == 2)) {
                        msg += ". " + LocaleController.getString(R.string.A11yLegacyDrawerRestart);
                    }
                    announce(activity, msg);
                })
                .setNegativeButton(LocaleController.getString(R.string.A11yCancel), null)
                .show();
    }

    public static final String PREF_LEGACY_DRAWER = "a11y_legacy_navigation_drawer";
    /** Read once when the main screen is created (LaunchActivity.onCreate): true = the classic navigation drawer. Default false. */
    public static boolean useLegacyNavigationDrawer = false;

    public static boolean getLegacyNavigationDrawer() {
        return getMenuStyle() == 2;
    }

    public static void setLegacyNavigationDrawer(boolean value) {
        setMenuStyle(value ? 2 : (getMenuStyle() == 2 ? 1 : getMenuStyle()));
    }

    public static void loadLegacyNavigationDrawer() {
        useLegacyNavigationDrawer = getLegacyNavigationDrawer();
    }

    public static final String PREF_FORWARD_HERE = "a11y_forward_here";

    /** "Forward here" item in the message options (re-sends the message into the same chat). Default OFF. */
    public static boolean getForwardHere() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_FORWARD_HERE, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setForwardHere(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_FORWARD_HERE, value).apply();
        } catch (Throwable ignore) {
        }
    }

    public static final String PREF_CATEGORY_FILTER = "a11y_category_filter";
    /** The chosen category of the chat list filter: 0 all, 1 private chats, 2 groups, 3 channels, 4 bots, 5 unread, 6 read. Not saved. */
    public static int categoryFilterValue = 0;

    /** Category filter (All / Private chats / Groups / Channels / Bots) for the chat list. Default OFF. */
    public static boolean getCategoryFilter() {
        try {
            return MessagesController.getGlobalMainSettings().getBoolean(PREF_CATEGORY_FILTER, false);
        } catch (Throwable ignore) {
            return false;
        }
    }

    public static void setCategoryFilter(boolean value) {
        try {
            MessagesController.getGlobalMainSettings().edit().putBoolean(PREF_CATEGORY_FILTER, value).apply();
        } catch (Throwable ignore) {
        }
    }

    private static java.util.ArrayList<String> buildSettingsItems() {
        final java.util.ArrayList<String> items = new java.util.ArrayList<>();
        items.add(LocaleController.formatString(R.string.A11yProgressAnnounceLabel, progressStepLabel()));
        items.add(LocaleController.formatString(R.string.A11yVoiceQualityLabel, voiceQualityLabel()));
        items.add(LocaleController.formatString(R.string.A11yHideSponsorLabel, onOff(getHideSponsorChannel())));
        items.add(LocaleController.formatString(R.string.A11yGhostModeLabel, onOff(getGhostMode())));
        items.add(LocaleController.formatString(R.string.A11yStatusPreviewLabel, onOff(getShowStatusInPreview())));
        items.add(LocaleController.formatString(R.string.A11yForwardSavedNoQuoteLabel, onOff(getForwardSavedNoQuote())));
        items.add(LocaleController.formatString(R.string.A11yRecordingBeepLabel, onOff(getRecordingBeep())));
        items.add(LocaleController.formatString(R.string.A11ySolarCalendarLabel, onOff(getSolarCalendar())));
        items.add(LocaleController.formatString(R.string.A11yLinksLabel, onOff(getLinksMenuEnabled())));
        items.add(getSmallFilesAutoDownloadModeAnnouncement());
        items.add(LocaleController.formatString(R.string.A11yDownloadStateLabel, onOff(getAnnounceDownloadState())));
        items.add(LocaleController.formatString(R.string.A11yAlbumReadingLabel, onOff(getAlbumReading())) + ". " + LocaleController.getString(R.string.A11yAlbumReadingSummary));
        items.add(LocaleController.formatString(R.string.A11yAdminTagLabel, onOff(getAdminTagAnnounce())) + ". " + LocaleController.getString(R.string.A11yAdminTagSummary));
        items.add(LocaleController.formatString(R.string.A11yUserStatusLabel, onOff(getUserStatusAnnounce())));
        items.add(LocaleController.formatString(R.string.A11yChatOpenSoundLabel, onOff(getChatOpenSound())));
        items.add(LocaleController.formatString(R.string.A11ySenderOptionsLabel, onOff(getSenderOptionsInMenu())));
        items.add(LocaleController.formatString(R.string.A11yVoiceShareSaveLabel, onOff(getVoiceShareSave())));
        items.add(LocaleController.formatString(R.string.A11yPlayerSeekLabel, onOff(getPlayerSeekButtons())));
        items.add(LocaleController.formatString(R.string.A11yProxyButtonLabel, onOff(getProxyButtonInToolbar())));
        items.add(LocaleController.formatString(R.string.A11yMenuStyleLabel, menuStyleLabels()[getMenuStyle()]));
        items.add(LocaleController.formatString(R.string.A11yCategoryLabel, onOff(getCategoryFilter())));
        items.add(LocaleController.formatString(R.string.A11yForwardHereLabel, onOff(getForwardHere())));
        return items;
    }

    public static void showSettingsDialog(final Activity activity) {
        if (activity == null) {
            return;
        }
        try {
            final java.util.ArrayList<String> items = buildSettingsItems();
            final android.widget.ArrayAdapter<String> adapter =
                    new android.widget.ArrayAdapter<>(activity, android.R.layout.simple_list_item_1, items);
            final Runnable refresh = () -> {
                items.clear();
                items.addAll(buildSettingsItems());
                adapter.notifyDataSetChanged();
            };
            final AlertDialog dialog = new AlertDialog.Builder(activity)
                    .setTitle(LocaleController.getString(R.string.A11yAccessibleSettingsTitle))
                    .setAdapter(adapter, null)
                    .setNegativeButton(LocaleController.getString(R.string.A11yClose), null)
                    .create();
            dialog.show();
            // the stock click handler dismisses the dialog; ours only refreshes the row
            dialog.getListView().setOnItemClickListener((parent, view, which, id) -> handleSettingsClick(activity, which, refresh));
        } catch (Throwable ignore) {
        }
    }

    private static void handleSettingsClick(final Activity activity, int which, final Runnable refresh) {
        try {
            String message = null;
            switch (which) {
                case 0:
                    showProgressStepPicker(activity, refresh);
                    return;
                case 1:
                    showVoiceQualityPicker(activity, refresh);
                    return;
                case 2:
                    setHideSponsorChannel(!getHideSponsorChannel());
                    message = LocaleController.getString(getHideSponsorChannel() ? R.string.A11ySponsorHidden : R.string.A11ySponsorShown);
                    break;
                case 3:
                    setGhostMode(!getGhostMode());
                    message = LocaleController.getString(getGhostMode() ? R.string.A11yGhostOn : R.string.A11yGhostOff);
                    break;
                case 4:
                    setShowStatusInPreview(!getShowStatusInPreview());
                    message = LocaleController.getString(getShowStatusInPreview() ? R.string.A11yStatusOn : R.string.A11yStatusOff);
                    break;
                case 5:
                    setForwardSavedNoQuote(!getForwardSavedNoQuote());
                    message = LocaleController.formatString(R.string.A11yForwardSavedNoQuoteLabel, onOff(getForwardSavedNoQuote()));
                    break;
                case 6:
                    setRecordingBeep(!getRecordingBeep());
                    message = LocaleController.formatString(R.string.A11yRecordingBeepLabel, onOff(getRecordingBeep()));
                    break;
                case 7:
                    setSolarCalendar(!getSolarCalendar());
                    message = LocaleController.formatString(R.string.A11ySolarCalendarLabel, onOff(getSolarCalendar()));
                    break;
                case 8:
                    setLinksMenuEnabled(!getLinksMenuEnabled());
                    message = LocaleController.formatString(R.string.A11yLinksLabel, onOff(getLinksMenuEnabled()));
                    break;
                case 9:
                    showSmallFilesModePicker(activity, refresh);
                    return;
                case 10:
                    setAnnounceDownloadState(!getAnnounceDownloadState());
                    message = LocaleController.formatString(R.string.A11yDownloadStateLabel, onOff(getAnnounceDownloadState()));
                    break;
                case 11:
                    setAlbumReading(!getAlbumReading());
                    message = LocaleController.formatString(R.string.A11yAlbumReadingLabel, onOff(getAlbumReading()));
                    break;
                case 12:
                    setAdminTagAnnounce(!getAdminTagAnnounce());
                    message = LocaleController.formatString(R.string.A11yAdminTagLabel, onOff(getAdminTagAnnounce()));
                    break;
                case 13:
                    setUserStatusAnnounce(!getUserStatusAnnounce());
                    message = LocaleController.formatString(R.string.A11yUserStatusLabel, onOff(getUserStatusAnnounce()));
                    break;
                case 14:
                    setChatOpenSound(!getChatOpenSound());
                    message = LocaleController.formatString(R.string.A11yChatOpenSoundLabel, onOff(getChatOpenSound()));
                    break;
                case 15:
                    setSenderOptionsInMenu(!getSenderOptionsInMenu());
                    message = LocaleController.formatString(R.string.A11ySenderOptionsLabel, onOff(getSenderOptionsInMenu()));
                    break;
                case 16:
                    setVoiceShareSave(!getVoiceShareSave());
                    message = LocaleController.formatString(R.string.A11yVoiceShareSaveLabel, onOff(getVoiceShareSave()));
                    break;
                case 17:
                    setPlayerSeekButtons(!getPlayerSeekButtons());
                    message = LocaleController.formatString(R.string.A11yPlayerSeekLabel, onOff(getPlayerSeekButtons()));
                    break;
                case 18:
                    setProxyButtonInToolbar(!getProxyButtonInToolbar());
                    message = LocaleController.formatString(R.string.A11yProxyButtonLabel, onOff(getProxyButtonInToolbar()));
                    break;
                case 19:
                    showMenuStylePicker(activity, refresh);
                    return;
                case 20:
                    setCategoryFilter(!getCategoryFilter());
                    if (!getCategoryFilter()) {
                        categoryFilterValue = 0;
                    }
                    try {
                        org.telegram.ui.DialogsActivity.a11yRefreshCategory();
                    } catch (Throwable ignore) {
                    }
                    message = LocaleController.formatString(R.string.A11yCategoryLabel, onOff(getCategoryFilter()));
                    break;
                case 21:
                    setForwardHere(!getForwardHere());
                    message = LocaleController.formatString(R.string.A11yForwardHereLabel, onOff(getForwardHere()));
                    break;
                default:
                    return;
            }
            refresh.run();
            announce(activity, message);
        } catch (Throwable ignore) {
        }
    }

    private static void showProgressStepPicker(final Activity activity, final Runnable onChanged) {
        final int[] steps = new int[]{1, 5, 10, 20};
        final String[] labels = new String[steps.length];
        for (int i = 0; i < steps.length; i++) {
            labels[i] = LocaleController.formatString(R.string.A11yProgressStepLabel, steps[i]);
        }
        int cur = getProgressStep();
        int checked = 0;
        for (int i = 0; i < steps.length; i++) {
            if (steps[i] == cur) checked = i;
        }
        new AlertDialog.Builder(activity)
                .setTitle(LocaleController.getString(R.string.A11yProgressStepPickerTitle))
                .setSingleChoiceItems(labels, checked, (d, which) -> {
                    setProgressStep(steps[which]);
                    d.dismiss();
                    if (onChanged != null) onChanged.run();
                    announce(activity, labels[which]);
                })
                .setNegativeButton(LocaleController.getString(R.string.A11yCancel), null)
                .show();
    }

    private static void showVoiceQualityPicker(final Activity activity, final Runnable onChanged) {
        final String[] labels = new String[]{
                LocaleController.getString(R.string.A11yVoiceLow),
                LocaleController.getString(R.string.A11yVoiceMedium),
                LocaleController.getString(R.string.A11yVoiceHigh)
        };
        int checked = getVoiceQuality();
        if (checked < 0 || checked > 2) checked = 1;
        new AlertDialog.Builder(activity)
                .setTitle(LocaleController.getString(R.string.A11yVoiceQualityPickerTitle))
                .setSingleChoiceItems(labels, checked, (d, which) -> {
                    setVoiceQuality(which);
                    d.dismiss();
                    if (onChanged != null) onChanged.run();
                    announce(activity, labels[which]);
                })
                .setNegativeButton(LocaleController.getString(R.string.A11yCancel), null)
                .show();
    }

    private static void showSmallFilesModePicker(final Activity activity, final Runnable onChanged) {
        final String[] labels = new String[]{
                LocaleController.getString(R.string.A11ySmallFilesAuto),
                LocaleController.getString(R.string.A11ySmallFilesVoiceOnly),
                LocaleController.getString(R.string.A11ySmallFilesOff)
        };
        new AlertDialog.Builder(activity)
                .setTitle(LocaleController.getString(R.string.A11ySmallFilesPickerTitle))
                .setSingleChoiceItems(labels, getSmallFilesAutoDownloadMode(), (d, which) -> {
                    setSmallFilesAutoDownloadMode(which);
                    d.dismiss();
                    if (onChanged != null) onChanged.run();
                    announce(activity, getSmallFilesAutoDownloadModeAnnouncement());
                })
                .setNegativeButton(LocaleController.getString(R.string.A11yCancel), null)
                .show();
    }
"""
    last = t.rstrip().rfind("}")
    t = t[:last] + new_code + "\n" + t[last:]
    cfgp.write_text(t, encoding="utf-8")
    print("A11yConfig settings dialog stays open + download-state setting OK")


def patch_admin_tag_switch() -> None:
    """Accessible Settings switch "Announce admin and group tags" (default OFF).

    Telegram speaks the admin / owner / member tag after the sender's name in groups. With the
    switch off nothing of it is spoken; with it on the stock wording is unchanged.
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    _gate_once(
        cmc,
        "                        final CharSequence adminText = getAdminAccessibilityText();\n",
        "                        final CharSequence adminText = org.telegram.messenger.A11yConfig.getAdminTagAnnounce() ? getAdminAccessibilityText() : null; // a11y-fork: setting (default OFF)\n",
        "ChatMessageCell admin-tag switch")


LEAVE_COMMENT_MENU_BLOCK = (
    "        // a11y-fork: leave comment menu v1\n"
    "        try {\n"
    "            final MessageObject a11yCommentMsg = groupedMessages != null && !groupedMessages.messages.isEmpty() ? groupedMessages.messages.get(0) : message;\n"
    "            if (a11yCommentMsg != null && a11yCommentMsg.messageOwner != null && a11yCommentMsg.messageOwner.action == null\n"
    "                    && chatMode != MODE_SCHEDULED && chatMode != MODE_WELCOME_MESSAGES\n"
    "                    && ChatObject.isChannel(currentChat) && currentChat.has_link && !currentChat.megagroup\n"
    "                    && !message.isEphemeral() && !message.isSponsored()\n"
    "                    && a11yCommentMsg.isLinkedToChat(chatInfo != null ? chatInfo.linked_chat_id : 0)) {\n"
    "                final int a11yCommentCount = a11yCommentMsg.getRepliesCount();\n"
    "                items.add(0, a11yCommentCount <= 0\n"
    "                        ? LocaleController.getString(R.string.A11yLeaveComment)\n"
    "                        : a11yCommentCount == 1\n"
    "                        ? LocaleController.getString(R.string.A11yCommentOne)\n"
    "                        : LocaleController.formatString(\"A11yCommentsCount\", R.string.A11yCommentsCount, a11yCommentCount));\n"
    f"                options.add(0, {OPTION_LEAVE_COMMENT});\n"
    "                icons.add(0, R.drawable.msg_viewreplies);\n"
    "            }\n"
    "        } catch (Throwable e) {\n"
    "            FileLog.e(e);\n"
    "        }\n\n"
)


def patch_leave_comment_menu() -> None:
    """Bring back "Leave comment" (with the comment count) as an item of the message options.

    The comment button that Telegram draws under channel posts is hidden for TalkBack
    (patch_hide_share_and_comment), so this item replaces it: it appears for the same posts the
    button appears for (channel with a linked discussion group, post with comments enabled),
    reads "Leave comment" when there are none and "4 comments" when there are, and opens the
    discussion exactly like a tap on the button (same arguments as didPressCommentButton).
    The item is placed by patch_reorder_a11y_menu_items (after Bot Buttons, before Reactions).
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (leave comment menu)")
        return
    t = ca.read_text(encoding="utf-8")

    if "a11y-fork: OPTION_LEAVE_COMMENT declaration" not in t:
        class_idx = t.find("public class ChatActivity")
        brace_idx = t.find("{", class_idx) if class_idx != -1 else -1
        if brace_idx == -1:
            print("WARN: ChatActivity class brace not found (leave comment menu)")
            return
        t = (t[:brace_idx + 1]
             + "\n    private static final int OPTION_LEAVE_COMMENT = %d; // a11y-fork: OPTION_LEAVE_COMMENT declaration\n" % OPTION_LEAVE_COMMENT
             + t[brace_idx + 1:])

    if "a11y-fork: leave comment handler" not in t:
        old_case = "            case OPTION_RETRY: {\n"
        new_case = (
            "            case OPTION_LEAVE_COMMENT: { // a11y-fork: leave comment handler\n"
            "                try {\n"
            "                    final MessageObject.GroupedMessages a11yGroup = selectedObjectGroup;\n"
            "                    final MessageObject a11yMsg = a11yGroup != null && !a11yGroup.messages.isEmpty() ? a11yGroup.messages.get(0) : selectedObject;\n"
            "                    if (a11yMsg != null && a11yMsg.messageOwner != null && currentChat != null) {\n"
            "                        final int a11yMaxReadId;\n"
            "                        final long a11yLinkedChatId;\n"
            "                        if (a11yMsg.messageOwner.replies != null) {\n"
            "                            a11yMaxReadId = a11yMsg.messageOwner.replies.read_max_id;\n"
            "                            a11yLinkedChatId = a11yMsg.messageOwner.replies.channel_id;\n"
            "                        } else {\n"
            "                            a11yMaxReadId = -1;\n"
            "                            a11yLinkedChatId = 0;\n"
            "                        }\n"
            "                        openDiscussionMessageChat(currentChat.id, a11yMsg, a11yMsg.getId(), a11yLinkedChatId, a11yMaxReadId, 0, null);\n"
            "                    }\n"
            "                } catch (Throwable e) {\n"
            "                    FileLog.e(e);\n"
            "                }\n"
            "                selectedObject = null;\n"
            "                selectedObjectToEditCaption = null;\n"
            "                selectedObjectGroup = null;\n"
            "                break;\n"
            "            }\n"
            "            case OPTION_RETRY: {\n"
        )
        if t.count(old_case) != 1:
            print("WARN: OPTION_RETRY case anchor found %d times (leave comment handler)" % t.count(old_case))
            return
        t = t.replace(old_case, new_case, 1)

    if "a11y-fork: leave comment menu v1" not in t:
        anchor = ("        if (message.isSponsored() && !getUserConfig().isPremium() "
                  "&& !getMessagesController().premiumFeaturesBlocked() && !message.sponsoredCanReport) {\n")
        if t.count(anchor) != 1:
            print("WARN: sponsored-item anchor found %d times (leave comment menu item)" % t.count(anchor))
            return
        t = t.replace(anchor, LEAVE_COMMENT_MENU_BLOCK + anchor, 1)

    ca.write_text(t, encoding="utf-8")
    print("ChatActivity leave-comment menu item+handler OK")


def patch_share_send_button_label() -> None:
    """Label the send button of the share sheet ("Share in 3 chats").

    In ShareAlert the label was put on the focusable FRAME around the button, but the frame has
    no click listener -- the real, clickable button is its child (a bare View), which had no
    description at all, so TalkBack read an unlabeled button. Now the button itself carries
    "Share in N chats" (updated whenever the selection changes) and the empty frame is hidden
    from TalkBack so there is a single, correct stop. The forward picker (DialogsActivity) gets
    the same text as a content description as well.
    """
    sa = JAVA / "org/telegram/ui/Components/ShareAlert.java"
    _gate_once(
        sa,
        "        writeButtonContainer.setFocusableInTouchMode(true);\n",
        "        writeButtonContainer.setFocusableInTouchMode(true);\n"
        "        writeButtonContainer.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO); // a11y-fork: the real button is the child\n",
        "ShareAlert frame hidden from TalkBack")
    _gate_once(
        sa,
        "            writeButton.setCount(Math.max(1, selectedDialogs.size()), animated != 0);\n",
        "            writeButton.setCount(Math.max(1, selectedDialogs.size()), animated != 0);\n"
        "            writeButton.setContentDescription(LocaleController.formatPluralString(\"AccDescrShareInChats\", Math.max(1, selectedDialogs.size()))); // a11y-fork: send button label\n",
        "ShareAlert send button label")
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "                    info.setText(LocaleController.formatPluralString(\"AccDescrShareInChats\", selectedDialogs.size()));\n",
        "                    info.setText(LocaleController.formatPluralString(\"AccDescrShareInChats\", selectedDialogs.size()));\n"
        "                    info.setContentDescription(LocaleController.formatPluralString(\"AccDescrShareInChats\", selectedDialogs.size())); // a11y-fork\n",
        "DialogsActivity send button description")


def patch_every_node_long_click() -> None:
    """A long press (TalkBack double-tap-and-hold) must open Message Options wherever the focus is.

    A node without a LONG_CLICK action makes TalkBack send a real touch held at the node's middle,
    which Telegram reads as a tap on that spot (jump to the replied message, open a profile ...).
      1. every virtual node of a message cell advertises LONG_CLICK (routed to Message Options)
      2. service messages (ChatActionCell: "pinned a message", ...) get it too
      3. ChatActivity.createMenu: the "jump to the replied / pinned message" shortcut of the
         single-message path is for TAPS only, never for a long press
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    if cmc.exists():
        t = cmc.read_text(encoding="utf-8")
        marker = "a11y-fork: every virtual node answers a long press"
        old = "        @Override\n        public AccessibilityNodeInfo createAccessibilityNodeInfo(int virtualViewId) {\n"
        if marker in t:
            print("ChatMessageCell every-node long-click already patched")
        elif t.count(old) == 1:
            new = (
                "        // " + marker + "\n"
                "        @Override\n"
                "        public AccessibilityNodeInfo createAccessibilityNodeInfo(int virtualViewId) {\n"
                "            final AccessibilityNodeInfo a11yInfo = a11yCreateAccessibilityNodeInfo(virtualViewId);\n"
                "            try {\n"
                "                if (a11yInfo != null && virtualViewId != HOST_VIEW_ID) {\n"
                "                    boolean a11yHasLong = false;\n"
                "                    final java.util.List<AccessibilityNodeInfo.AccessibilityAction> a11yActions = a11yInfo.getActionList();\n"
                "                    if (a11yActions != null) {\n"
                "                        for (int a11yI = 0; a11yI < a11yActions.size(); a11yI++) {\n"
                "                            if (a11yActions.get(a11yI).getId() == AccessibilityNodeInfo.ACTION_LONG_CLICK) {\n"
                "                                a11yHasLong = true;\n"
                "                                break;\n"
                "                            }\n"
                "                        }\n"
                "                    }\n"
                "                    if (!a11yHasLong) {\n"
                "                        a11yInfo.addAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);\n"
                "                    }\n"
                "                }\n"
                "            } catch (Throwable ignore) {\n"
                "            }\n"
                "            return a11yInfo;\n"
                "        }\n\n"
                "        private AccessibilityNodeInfo a11yCreateAccessibilityNodeInfo(int virtualViewId) {\n"
            )
            t = t.replace(old, new, 1)
            cmc.write_text(t, encoding="utf-8")
            print("ChatMessageCell every-node long-click OK")
        else:
            print("WARN: ChatMessageCell provider createAccessibilityNodeInfo anchor not found exactly once")
    cac = JAVA / "org/telegram/ui/Cells/ChatActionCell.java"
    if cac.exists():
        t = cac.read_text(encoding="utf-8")
        marker = "a11y-fork: service message long-click"
        if marker in t:
            print("ChatActionCell long-click already patched")
        else:
            # works on plain upstream AND on the fork-merged tree: first setEnabled(true) of
            # onInitializeAccessibilityNodeInfo, and performAccessibilityAction (added if missing)
            n = t.find("public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {")
            k = t.find("        info.setEnabled(true);\n", n) if n >= 0 else -1
            if k < 0:
                print("WARN: ChatActionCell accessibility anchors not found")
            else:
                k += len("        info.setEnabled(true);\n")
                t = t[:k] + "        info.addAction(AccessibilityNodeInfo.ACTION_LONG_CLICK); // " + marker + "\n" + t[k:]
                body = (
                    "        if (action == AccessibilityNodeInfo.ACTION_LONG_CLICK) { // " + marker + "\n"
                    "            try {\n"
                    "                if (delegate != null) {\n"
                    "                    delegate.didLongPress(this, getWidth() / 2f, getHeight() / 2f);\n"
                    "                }\n"
                    "            } catch (Throwable ignore) {\n"
                    "            }\n"
                    "            return true;\n"
                    "        }\n"
                )
                sig = "    public boolean performAccessibilityAction(int action, Bundle arguments) {\n"
                if sig in t:
                    t = t.replace(sig, sig + body, 1)
                else:
                    anchor = "    public void setInvalidateColors(boolean invalidate) {\n"
                    if anchor in t and "import android.os.Bundle;" in t:
                        t = t.replace(anchor, "    @Override\n" + sig + body + "        return super.performAccessibilityAction(action, arguments);\n    }\n\n" + anchor, 1)
                    elif anchor in t:
                        t = t.replace(anchor, "    @Override\n    public boolean performAccessibilityAction(int action, android.os.Bundle arguments) {\n" + body + "        return super.performAccessibilityAction(action, arguments);\n    }\n\n" + anchor, 1)
                    else:
                        print("WARN: ChatActionCell performAccessibilityAction anchor not found")
                cac.write_text(t, encoding="utf-8")
                print("ChatActionCell long-click OK")
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if ca.exists():
        t = ca.read_text(encoding="utf-8")
        marker = "a11y-fork: no reply jump on long press"
        if marker in t:
            print("ChatActivity createMenu reply-jump guard already patched")
        else:
            edits = [
                ("            if (message.messageOwner.action instanceof TLRPC.TL_messageActionPollAppendAnswer) {\n                if (message.getReplyMsgId() != 0) {",
                 "            if (!longpress && message.messageOwner.action instanceof TLRPC.TL_messageActionPollAppendAnswer) { // " + marker + "\n                if (message.getReplyMsgId() != 0) {"),
                ("            if (message.messageOwner.action instanceof TLRPC.TL_messageActionPollDeleteAnswer) {\n                if (message.getReplyMsgId() != 0) {",
                 "            if (!longpress && message.messageOwner.action instanceof TLRPC.TL_messageActionPollDeleteAnswer) {\n                if (message.getReplyMsgId() != 0) {"),
                ("            if (message.messageOwner.action instanceof TLRPC.TL_messageActionPinMessage || isGiveawayResultsMessage) {\n",
                 "            if (!longpress && (message.messageOwner.action instanceof TLRPC.TL_messageActionPinMessage || isGiveawayResultsMessage)) {\n"),
            ]
            ok = 0
            for o, n in edits:
                if t.count(o) == 1:
                    t = t.replace(o, n, 1)
                    ok += 1
                else:
                    print("WARN: createMenu anchor count != 1: " + o.strip()[:70])
            if ok:
                ca.write_text(t, encoding="utf-8")
                print("ChatActivity createMenu: long press never jumps to the replied / pinned message (%d/3)" % ok)


def patch_stuck_together_bubbles_long_press() -> None:
    """Accessibility-fork: keep long-press coordinates inside the cell.

    The accessibility long-click path passes lastTouchX/lastTouchY (possibly stale, from an
    earlier touch on a different/recycled cell, or from a neighbouring bubble of a
    stuck-together cluster). The real ChatMessageCellDelegate.didLongPress implementation
    lives in ChatActivity -- ChatMessageCell only declares an EMPTY default method, which is
    where the previous revision looked (so it never applied and warned on every build).
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (long-press coordinate clamp)")
        return
    t = ca.read_text(encoding="utf-8")
    marker = "a11y-fork: clamp long-press coordinates"
    if marker in t:
        print("ChatActivity clamp long-press already patched")
        return
    ms = list(re.finditer(
        r"(?m)^([ \t]*)public void didLongPress\(ChatMessageCell cell, float x, float y\) \{\n", t))
    if len(ms) != 1:
        print("WARN: ChatActivity didLongPress(ChatMessageCell,x,y) implementation not found exactly once:", len(ms))
        return
    m = ms[0]
    inner = m.group(1) + "    "
    clamp = (
        f"{inner}// {marker}\n"
        f"{inner}if (cell != null) {{\n"
        f"{inner}    int a11yW = cell.getWidth();\n"
        f"{inner}    int a11yH = cell.getHeight();\n"
        f"{inner}    if (a11yW > 0 && (x < 0f || x >= (float) a11yW)) {{\n"
        f"{inner}        x = Math.max(1f, Math.min((float) a11yW - 2f, x));\n"
        f"{inner}    }}\n"
        f"{inner}    if (a11yH > 0 && (y < 0f || y >= (float) a11yH)) {{\n"
        f"{inner}        y = Math.max(1f, Math.min((float) a11yH - 2f, y));\n"
        f"{inner}    }}\n"
        f"{inner}}}\n"
    )
    t = t[:m.end()] + clamp + t[m.end():]
    ca.write_text(t, encoding="utf-8")
    print("ChatActivity clamp long-press OK")

def patch_reorder_a11y_menu_items() -> None:
    """Move Select / Reactions / Bot Buttons / Links out of their original
    early insertion point (right before the sponsored-ad block, i.e. near
    the TOP of the menu) and place them, in this exact order, at the very
    END of fillMessageMenu -- after every native item (Copy, Delete, Reply,
    Report, Save to Downloads/Gallery, etc.), right before the method's
    closing brace. Must run after patch_longpress_message_menu,
    patch_reactions_as_menu, patch_bot_buttons_menu and patch_links_as_menu,
    since it relocates the exact blocks those functions insert.
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    if not ca.exists():
        print("WARN: ChatActivity missing (menu reorder)")
        return
    t = ca.read_text(encoding="utf-8")
    marker = "a11y-fork: menu items reordered to end-v1"
    if marker in t:
        print("ChatActivity a11y menu items already reordered")
        return

    blocks = {
        "links": (
            "        // a11y-fork: links menu v1\n"
            "        if (org.telegram.messenger.A11yConfig.getLinksMenuEnabled() && message != null && a11yMessageHasLinks(message)) {\n"
            "            items.add(LocaleController.getString(R.string.A11yLinks));\n"
            "            options.add(OPTION_LINKS_MENU);\n"
            "            icons.add(R.drawable.msg_forward);\n"
            "        }\n\n"
        ),
        "bot_buttons": (
            "        // a11y-fork: bot buttons menu\n"
            "        if (message != null && message.hasInlineBotButtons()) {\n"
            "            items.add(\"Bot Buttons\");\n"
            "            options.add(OPTION_BOT_BUTTONS_MENU);\n"
            "            icons.add(R.drawable.msg_viewreplies);\n"
            "        }\n\n"
        ),
        "leave_comment": LEAVE_COMMENT_MENU_BLOCK,
        "reactions": (
            "        // a11y-fork: reactions menu item\n"
            "        accessibilityReactionsToggleIndex = -1;\n"
            "        if (isReactionsAvailableFinal) {\n"
            "            items.add(LocaleController.getString(R.string.Reactions));\n"
            "            icons.add(R.drawable.msg_reactions2);\n"
            f"            options.add({OPTION_REACTIONS_MENU});\n"
            "            accessibilityReactionsToggleIndex = items.size() - 1;\n"
            "        }\n\n"
        ),
        "select": (
            "        // a11y-fork: OPTION_SELECT_MESSAGE menu\n"
            "        if (!actionBar.isActionModeShowed() && message != null && message.contentType == 0 && !message.isSponsored()) {\n"
            "            items.add(LocaleController.getString(R.string.Select));\n"
            f"            options.add({OPTION_SELECT_MESSAGE});\n"
            "            icons.add(R.drawable.msg_forward);\n"
            "        }\n\n"
        ),
    }

    optional = {"leave_comment"}  # never blocks the reorder if its patch did not apply
    blocks = {name: block for name, block in blocks.items() if name not in optional or block in t}
    missing = [name for name, block in blocks.items() if block not in t]
    if missing:
        print(f"WARN: a11y menu-item block(s) not found for reorder: {', '.join(missing)} (left in original position)")
        return

    for block in blocks.values():
        t = t.replace(block, "", 1)

    fmm_idx = t.find("public void fillMessageMenu(")
    if fmm_idx < 0:
        print("WARN: fillMessageMenu not found (menu reorder)")
        return
    open_paren_close = t.find(") {", fmm_idx)
    brace_idx = t.find("{", open_paren_close if open_paren_close >= 0 else fmm_idx)
    if brace_idx < 0:
        print("WARN: fillMessageMenu opening brace not found (menu reorder)")
        return
    depth = 0
    i = brace_idx
    end_idx = -1
    while i < len(t):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break
        i += 1
    if end_idx < 0:
        print("WARN: fillMessageMenu closing brace not found (menu reorder)")
        return

    ordered = (
        f"        // {marker} -- order: Links, Bot Buttons, Leave Comment, Reactions, Select\n"
        + blocks["links"] + blocks["bot_buttons"] + blocks.get("leave_comment", "") + blocks["reactions"] + blocks["select"]
    )
    t = t[:end_idx] + ordered + t[end_idx:]
    ca.write_text(t, encoding="utf-8")
    print("ChatActivity a11y menu items reordered to end (Links, Bot Buttons, Leave Comment, Reactions, Select) OK")




def patch_small_file_localization() -> None:
    """Add localized labels required by the 3-state small-file setting."""
    en = {
        "A11ySmallFilesModeLabel": "Small files auto-download: %s",
        "A11ySmallFilesAuto": "Auto-download small files",
        "A11ySmallFilesVoiceOnly": "Do not download small files except voice messages",
        "A11ySmallFilesOff": "Do not download small files",
        "A11ySmallFilesPickerTitle": "Small files auto-download",
    }
    fa = {
        "A11ySmallFilesModeLabel": "دانلود خودکار فایل‌های کم‌حجم: %s",
        "A11ySmallFilesAuto": "دانلود خودکار فایل‌های کم‌حجم",
        "A11ySmallFilesVoiceOnly": "دانلود نکردن فایل‌های کم‌حجم به‌جز پیام‌های صوتی",
        "A11ySmallFilesOff": "دانلود نکردن فایل‌های کم‌حجم",
        "A11ySmallFilesPickerTitle": "دانلود خودکار فایل‌های کم‌حجم",
    }
    for rel, values in (("values/strings.xml", en), ("values-fa/strings.xml", fa), ("values-fa-rIR/strings.xml", fa)):
        path = RES / rel
        if not path.exists():
            continue
        for name, value in values.items():
            _set_string(path, name, value)
    print("Small-file 3-state localization OK")

def patch_small_file_download_mode() -> None:
    """One clean, authoritative 3-state "small files" auto-download setting.

    0 SMALL_FILES_AUTO       small files (<=512 KB) auto-download of every type, on networks where
                             Telegram's own auto-download master switch is on
    1 SMALL_FILES_VOICE_ONLY block small (<=512 KB) auto-downloads except voice messages (default)
    2 SMALL_FILES_OFF        block ALL small (<=512 KB) auto-downloads AND all voice messages of
                             any size (voice bypasses Telegram's per-type switches)

    Replaces the old stack of overlapping v10..v20 patches. Those left the settings row
    labelled with the legacy "voice-only: On/Off" text while its click opened the radio
    picker, kept two dead click handlers, and -- worst -- kept a legacy voice-only flag whose
    default was TRUE and which blocked every non-voice auto-download regardless of the radio
    choice (so "Auto-download small files" could never work).
    All blocking logic now lives in ONE method, A11yConfig.blockAutoDownload(type, size),
    called from every DownloadController decision point.
    """
    cfg = JAVA / "org/telegram/messenger/A11yConfig.java"
    dc = JAVA / "org/telegram/messenger/DownloadController.java"
    if not cfg.exists() or not dc.exists():
        print("WARN: A11yConfig/DownloadController missing (small-file download mode)")
        return

    # ---------- A11yConfig.java ----------
    c = cfg.read_text(encoding="utf-8")
    marker = "a11y-fork: small-file download mode v3"
    if marker not in c:
        methods = r"""    // a11y-fork: small-file download mode v3
    // 0 = fork adds no restriction, 1 = block small files except voice (default),
    // 2 = block all small files (voice included).
    public static final int SMALL_FILES_AUTO = 0;
    public static final int SMALL_FILES_VOICE_ONLY = 1;
    public static final int SMALL_FILES_OFF = 2;
    public static final long SMALL_FILE_MAX_SIZE = 512 * 1024;
    private static final String PREF_SMALL_FILES_MODE = "a11y_small_files_mode";

    public static int getSmallFilesAutoDownloadMode() {
        try {
            int mode = MessagesController.getGlobalMainSettings().getInt(PREF_SMALL_FILES_MODE, SMALL_FILES_VOICE_ONLY);
            return mode < SMALL_FILES_AUTO || mode > SMALL_FILES_OFF ? SMALL_FILES_VOICE_ONLY : mode;
        } catch (Throwable ignore) {
            return SMALL_FILES_VOICE_ONLY;
        }
    }

    public static void setSmallFilesAutoDownloadMode(int mode) {
        if (mode < SMALL_FILES_AUTO || mode > SMALL_FILES_OFF) mode = SMALL_FILES_VOICE_ONLY;
        try {
            MessagesController.getGlobalMainSettings().edit().putInt(PREF_SMALL_FILES_MODE, mode).apply();
            try { DownloadController.getInstance(UserConfig.selectedAccount).checkAutodownloadSettings(); } catch (Throwable ignore) {}
        } catch (Throwable ignore) {
        }
    }

    public static String getSmallFilesAutoDownloadModeLabel() {
        switch (getSmallFilesAutoDownloadMode()) {
            case SMALL_FILES_AUTO:
                return LocaleController.getString(R.string.A11ySmallFilesAuto);
            case SMALL_FILES_OFF:
                return LocaleController.getString(R.string.A11ySmallFilesOff);
            default:
                return LocaleController.getString(R.string.A11ySmallFilesVoiceOnly);
        }
    }

    public static String getSmallFilesAutoDownloadModeAnnouncement() {
        return LocaleController.formatString(R.string.A11ySmallFilesModeLabel, getSmallFilesAutoDownloadModeLabel());
    }

    /** True when the fork must veto an automatic download of this type/size. */
    public static boolean blockAutoDownload(int type, long size) {
        try {
            int mode = getSmallFilesAutoDownloadMode();
            if (mode == SMALL_FILES_AUTO) {
                return false;
            }
            if (mode == SMALL_FILES_OFF) {
                // Telegram lets voice messages bypass the per-type switches entirely, so a
                // voice message bigger than 512 KB would still download by itself. "Off" has
                // to mean off: block every small file AND every voice message, whatever its size.
                return size <= SMALL_FILE_MAX_SIZE || type == DownloadController.AUTODOWNLOAD_TYPE_AUDIO;
            }
            if (size > SMALL_FILE_MAX_SIZE) {
                return false;
            }
            return type != DownloadController.AUTODOWNLOAD_TYPE_AUDIO;
        } catch (Throwable ignore) {
            return false;
        }
    }

    /** True when the fork must let this small automatic download through (AUTO mode only). */
    public static boolean allowSmallAutoDownload(int type, long size) {
        try {
            return getSmallFilesAutoDownloadMode() == SMALL_FILES_AUTO && size > 0 && size <= SMALL_FILE_MAX_SIZE;
        } catch (Throwable ignore) {
            return false;
        }
    }

    private static void showSmallFilesModePicker(Activity activity) {
        final String[] labels = new String[]{
                LocaleController.getString(R.string.A11ySmallFilesAuto),
                LocaleController.getString(R.string.A11ySmallFilesVoiceOnly),
                LocaleController.getString(R.string.A11ySmallFilesOff)
        };
        new AlertDialog.Builder(activity)
                .setTitle(LocaleController.getString(R.string.A11ySmallFilesPickerTitle))
                .setSingleChoiceItems(labels, getSmallFilesAutoDownloadMode(), (d, which) -> {
                    setSmallFilesAutoDownloadMode(which);
                    d.dismiss();
                    announce(activity, getSmallFilesAutoDownloadModeAnnouncement());
                })
                .setNegativeButton(LocaleController.getString(R.string.A11yCancel), null)
                .show();
    }

"""
        anchor = "    public static void showSettingsDialog(Activity activity) {"
        if anchor not in c:
            print("WARN: showSettingsDialog anchor not found (small-file download mode)")
            return
        c = c.replace(anchor, methods + anchor, 1)

        # settings-dialog row: appended after the LAST existing row, index = its position
        m = re.search(r'final String\[\] items = new String\[\]\{(.*?)\n            \};', c, re.S)
        if not m:
            print("WARN: settings items array not found (small-file download mode)")
            return
        body = m.group(1)
        row_count = body.count("LocaleController.formatString(") + body.count("getSmallFilesAutoDownloadModeAnnouncement()")
        new_body = body.rstrip() + ",\n                    getSmallFilesAutoDownloadModeAnnouncement()"
        c = c[:m.start(1)] + new_body + c[m.end(1):]
        handler_anchor = "                    })\n                    .setNegativeButton(LocaleController.getString(R.string.A11yCancel), null)\n                    .show();\n        } catch (Throwable ignore) {\n        }\n    }\n\n    private static void announce("
        # the items click-listener closes with `}` right before `})`
        hm = re.search(r'(\n                        \}\n)(                    \}\)\n                    \.setNegativeButton)', c)
        if not hm:
            print("WARN: settings click handler end not found (small-file download mode)")
            return
        c = c[:hm.start(1)] + (
            "\n                        } else if (which == %d) {\n"
            "                            showSmallFilesModePicker(activity);\n"
            "                        }\n" % row_count
        ) + c[hm.end(1):]
    cfg.write_text(c, encoding="utf-8")

    # ---------- DownloadController.java ----------
    d = dc.read_text(encoding="utf-8")
    if "a11y-fork: small-file hook v3" not in d:
        # every decision point ends in the same generic return, in 4 typed variants
        generic_bool = ("        long maxSize = preset.sizes[typeToIndex(type)];\n"
                        "        return (type == AUTODOWNLOAD_TYPE_PHOTO || size != 0 && size <= maxSize) && (type == AUTODOWNLOAD_TYPE_AUDIO || (mask & type) != 0);")
        if generic_bool in d:
            d = d.replace(generic_bool,
                "        // a11y-fork: small-file hook v3 (type/size path)\n"
                "        if (A11yConfig.blockAutoDownload(type, size)) {\n"
                "            return false;\n"
                "        }\n"
                "        if (A11yConfig.allowSmallAutoDownload(type, size)) {\n"
                "            return true;\n"
                "        }\n" + generic_bool, 1)
        else:
            print("WARN: DownloadController generic canDownloadMedia(type,size) anchor not found")
        ret_re = re.compile(r'(?m)^(            return \(type == AUTODOWNLOAD_TYPE_PHOTO \|\| size != 0 && size <= maxSize\) && \(type == AUTODOWNLOAD_TYPE_AUDIO \|\| \(mask & type\) != 0\) \? 1 : 0;)$')
        n_sites = len(ret_re.findall(d))
        d = ret_re.sub(
            "            // a11y-fork: small-file hook v3\n"
            "            if (A11yConfig.blockAutoDownload(type, size)) {\n"
            "                return 0;\n"
            "            }\n"
            "            if (A11yConfig.allowSmallAutoDownload(type, size)) {\n"
            "                return 1;\n"
            "            }\n"
            r"\1", d)
        print(f"DownloadController small-file hook installed at {n_sites} message/media sites + generic path")
        if n_sites != 4:
            print("WARN: expected 4 message/media decision sites in DownloadController, found", n_sites)
    dc.write_text(d, encoding="utf-8")
    print("Small-file 3-state download mode v2 OK")


def patch_exact_progress_steps() -> None:
    """Force the accessible progress picker/logic to the requested 1, 5, 10, 20 percent steps."""
    cfg = JAVA / "org/telegram/messenger/A11yConfig.java"
    if not cfg.exists():
        return
    t = cfg.read_text(encoding="utf-8")
    t2 = re.sub(r'int\[\]\s+steps\s*=\s*new\s+int\[\]\s*\{[^}]*\};',
                'int[] steps = new int[]{1, 5, 10, 20}; // a11y-fork: exact progress steps', t, count=1)
    t2 = re.sub(r'int\[\]\s+steps\s*=\s*\{[^}]*\};',
                'int[] steps = {1, 5, 10, 20}; // a11y-fork: exact progress steps', t2, count=1)
    if 'a11y-fork: exact progress steps' not in t2:
        t2 = t2.replace('new int[]{5, 10, 20, 50}', 'new int[]{1, 5, 10, 20} // a11y-fork: exact progress steps')
        t2 = t2.replace('new int[] {5, 10, 20, 50}', 'new int[] {1, 5, 10, 20} // a11y-fork: exact progress steps')
    cfg.write_text(t2, encoding="utf-8")
    print("Progress steps 1/5/10/20 OK")

def patch_dialog_row_tap_sound() -> None:
    """The click of a tap on a chat of the chat list comes at the tap, not when the chat opens.

    It used to come from the chat fragment starting to open, which is a moment after the tap.
    A TalkBack double tap on a chat row reaches DialogCell as ACTION_CLICK and is passed on to the
    list (RecyclerListView.clickItem); the click is played right there, before that, the same way as
    for a message (same switch, same A11yConfig). The chat that then opens stays quiet once
    (A11yConfig.playChatOpenSoundUnlessJustTapped); chats opened any other way still click as
    they open. That list hand-over exists only with the fork's patch; without it nothing is
    changed here and the click stays on the opening of the chat.
    """
    dc = JAVA / "org/telegram/ui/Cells/DialogCell.java"
    anchor = ("                if (action == AccessibilityNodeInfo.ACTION_CLICK) {\n"
              "                    list.clickItem(this, position, getMeasuredWidth() / 2f, getMeasuredHeight() / 2f);\n")
    if not dc.exists():
        print("WARN: DialogCell.java missing (row tap sound)")
        return
    t = dc.read_text(encoding="utf-8")
    if "playRowTapSound" in t:
        print("DialogCell row tap sound already patched")
        return
    if t.count(anchor) != 1:
        print("DialogCell row tap sound: list hand-over not present (%d), left as is" % t.count(anchor))
        return
    new = ("                if (action == AccessibilityNodeInfo.ACTION_CLICK) {\n"
           "                    org.telegram.messenger.A11yConfig.playRowTapSound(); // a11y-fork: click at the tap on a chat row\n"
           "                    list.clickItem(this, position, getMeasuredWidth() / 2f, getMeasuredHeight() / 2f);\n")
    dc.write_text(t.replace(anchor, new, 1), encoding="utf-8")
    print("DialogCell row tap sound OK")


def patch_proxy_toolbar_button() -> None:
    """The proxy button of the chat list's top bar, as older Telegram versions had it.

    Today the proxy entry sits inside the "More options" popup, and only while a proxy is on (or the
    country is blocked and a proxy list exists). Older versions had a button in the top bar for
    exactly the same condition. With the Accessible Settings switch "Proxy button in the chat list
    toolbar" (A11yConfig.getProxyButtonInToolbar, default OFF) that button comes back, after the
    downloads button and before More options. It opens the proxy list, and its name says the state:
    "Proxy settings, connected / connecting / disabled". It is refreshed whenever the bar's proxy
    state is (connection changes, coming back to the list), so a switch flipped in the settings shows
    up when you return to the chat list.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "    private ActionBarMenuSubItem proxyMenuSubItem;\n",
        "    private ActionBarMenuSubItem proxyMenuSubItem;\n"
        "    private ActionBarMenuItem a11yProxyItem; // a11y-fork: proxy button in the top bar (setting, default OFF)\n"
        "    private ProxyDrawable a11yProxyDrawable;\n",
        "DialogsActivity proxy toolbar fields")
    _gate_once(
        da,
        "            downloadsItem.setVisibility(View.GONE);\n"
        "\n"
        "            updateProxyButton(false, false);\n",
        "            downloadsItem.setVisibility(View.GONE);\n"
        "\n"
        "            // a11y-fork: proxy button in the top bar, as older versions had it\n"
        "            a11yProxyDrawable = new ProxyDrawable(context);\n"
        "            a11yProxyItem = menu.addItem(2, a11yProxyDrawable);\n"
        "            a11yProxyItem.setContentDescription(getString(R.string.ProxySettings));\n"
        "            a11yProxyItem.setVisibility(View.GONE);\n"
        "            a11yProxyItem.setOnClickListener(v -> presentFragment(new ProxyListActivity()));\n"
        "\n"
        "            updateProxyButton(false, false);\n",
        "DialogsActivity proxy toolbar button created")
    _gate_once(
        da,
        "        proxyDrawable.setConnected(proxyEnabled, connected, animated);\n"
        "    }\n",
        "        proxyDrawable.setConnected(proxyEnabled, connected, animated);\n"
        "        if (a11yProxyItem != null) { // a11y-fork: proxy button in the top bar\n"
        "            final boolean a11yProxyVisible = proxyEnabled && !TextUtils.isEmpty(preferences.getString(\"proxy_ip\", \"\"))\n"
        "                    || getMessagesController().blockedCountry && !SharedConfig.proxyList.isEmpty();\n"
        "            a11yProxyItem.setVisibility(org.telegram.messenger.A11yConfig.getProxyButtonInToolbar() && a11yProxyVisible ? View.VISIBLE : View.GONE);\n"
        "            if (a11yProxyDrawable != null) {\n"
        "                a11yProxyDrawable.setConnected(proxyEnabled, connected, animated);\n"
        "            }\n"
        "            a11yProxyItem.setContentDescription(getString(R.string.ProxySettings) + \", \" + getString(proxyEnabled ? (connected ? R.string.MenuProxyConnected : R.string.MenuProxyConnecting) : R.string.MenuProxyDisabled));\n"
        "        }\n"
        "    }\n",
        "DialogsActivity proxy toolbar refresh")


def patch_old_style_menu() -> None:
    """An old-style main menu (the old side drawer's entries) behind an Accessible Settings switch.

    Telegram removed the side drawer from its code; the old class cannot be put back without
    importing a whole older navigation. What can be given back is the menu itself: with the switch
    "Old-style main menu button in the chat list toolbar" (A11yConfig.getOldStyleMenu, default OFF)
    a button "Main menu" appears in the top bar of the chat list, before the proxy button. It opens a
    list with the drawer's entries -- the day / night switch first, My Profile, the side-menu bots, New Group, Contacts, Calls, Saved
    Messages, Settings, Invite Friends, Telegram Features -- each one opening the same screen the drawer opened. The
    bottom tabs of the current Telegram stay as they are. The switch is read when the chat list
    refreshes its top bar, so it shows when you come back to the list.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "    private ProxyDrawable a11yProxyDrawable;\n",
        "    private ProxyDrawable a11yProxyDrawable;\n"
        "    private ActionBarMenuItem a11yMenuItem; // a11y-fork: old-style main menu button (setting, default OFF)\n",
        "DialogsActivity old-style menu field")
    _gate_once(
        da,
        "            // a11y-fork: proxy button in the top bar, as older versions had it\n",
        "            a11yMenuItem = menu.addItem(6, R.drawable.msg_list); // a11y-fork: old-style main menu button, before the proxy button\n"
        "            a11yMenuItem.setContentDescription(getString(R.string.A11yMainMenu));\n"
        "            a11yMenuItem.setVisibility((org.telegram.messenger.A11yConfig.getOldStyleMenu() && !org.telegram.ui.LegacyDrawerHelper.isActive()) ? View.VISIBLE : View.GONE);\n"
        "            a11yMenuItem.setOnClickListener(v -> a11yShowOldStyleMenu());\n"
        "\n"
        "            // a11y-fork: proxy button in the top bar, as older versions had it\n",
        "DialogsActivity old-style menu button created")
    _gate_once(
        da,
        "        if (a11yProxyItem != null) { // a11y-fork: proxy button in the top bar\n",
        "        if (a11yMenuItem != null) { // a11y-fork: old-style main menu button\n"
        "            a11yMenuItem.setVisibility((org.telegram.messenger.A11yConfig.getOldStyleMenu() && !org.telegram.ui.LegacyDrawerHelper.isActive()) ? View.VISIBLE : View.GONE);\n"
        "        }\n"
        "        if (a11yProxyItem != null) { // a11y-fork: proxy button in the top bar\n",
        "DialogsActivity old-style menu refresh")
    _gate_once(
        da,
        "    private void showItemOptions() {\n",
        "    // a11y-fork: the entries of the old side drawer, each opening the screen the drawer opened\n"
        "    private void a11yShowOldStyleMenu() {\n"
        "        try {\n"
        "            ItemOptions io = ItemOptions.makeOptions(this, a11yMenuItem);\n"
        "            io.setColors(getThemedColor(Theme.key_actionBarDefaultTitle), getThemedColor(Theme.key_actionBarDefaultTitle));\n"
        "            io.setDimAlpha(0x08);\n"
        "            io.add(R.drawable.msg_openprofile, getString(R.string.MyProfile), () -> {\n"
        "                Bundle args = new Bundle();\n"
        "                args.putLong(\"user_id\", UserConfig.getInstance(currentAccount).getClientUserId());\n"
        "                presentFragment(new ProfileActivity(args, null));\n"
        "            });\n"
        "            io.add(R.drawable.outline_groups_24, getString(R.string.NewGroup), () -> presentFragment(new GroupCreateActivity(new Bundle())));\n"
        "            io.add(R.drawable.msg_contacts, getString(R.string.Contacts), () -> {\n"
        "                Bundle args = new Bundle();\n"
        "                args.putBoolean(\"needFinishFragment\", false);\n"
        "                presentFragment(new ContactsActivity(args));\n"
        "            });\n"
        "            io.add(R.drawable.msg_calls, getString(R.string.Calls), () -> presentFragment(new CallLogActivity()));\n"
        "            io.add(R.drawable.outline_saved_24, getString(R.string.SavedMessages), () -> {\n"
        "                Bundle args = new Bundle();\n"
        "                args.putLong(\"user_id\", UserConfig.getInstance(currentAccount).getClientUserId());\n"
        "                presentFragment(new ChatActivity(args));\n"
        "            });\n"
        "            io.add(R.drawable.msg_settings_old, getString(R.string.Settings), () -> presentFragment(new SettingsActivity()));\n"
        "            io.add(R.drawable.msg_invited, getString(R.string.InviteFriends), () -> presentFragment(new InviteContactsActivity()));\n"
        "            io.add(R.drawable.msg_help, getString(R.string.TelegramFeatures), () -> Browser.openUrl(getParentActivity(), getString(R.string.TelegramFeaturesUrl)));\n"
        "            io.show();\n"
        "            io.setTranslationY(-dp(64));\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n"
        "    }\n\n"
        "    private void showItemOptions() {\n",
        "DialogsActivity old-style menu list")


def patch_old_menu_hides_tabs() -> None:
    """With the old-style main menu on, the bottom tab bar is hidden; with it off, the bar is there.

    Telegram already hides the bar by itself (while searching, for instance) through
    MainTabsActivity's tabs-visible animator, driven by DialogsActivity.checkUi_mainTabsVisible ->
    MainTabsActivityController.setTabsVisible. That one entry is used here: what a screen asks for
    is remembered, and the bar is shown only if it asks for it AND the old-style menu is off. The
    state is also applied when the main screen comes back (onResume) and right when the switch
    in Accessible Settings is flipped (MainTabsActivity.a11yRefreshTabs), so the bar goes or comes
    without a restart. The tab pages themselves are untouched, and the menu's own entries reach
    Contacts, Calls and Settings.
    """
    mt = JAVA / "org/telegram/ui/MainTabsActivity.java"
    _gate_once(
        mt,
        "    private final BoolAnimator animatorTabsVisible = new BoolAnimator(ANIMATOR_ID_TABS_VISIBLE,\n"
        "        this, CubicBezierInterpolator.EASE_OUT_QUINT, 380, true);\n",
        "    private final BoolAnimator animatorTabsVisible = new BoolAnimator(ANIMATOR_ID_TABS_VISIBLE,\n"
        "        this, CubicBezierInterpolator.EASE_OUT_QUINT, 380, true);\n"
        "\n"
        "    // a11y-fork: bottom tabs hidden while the old-style main menu is on\n"
        "    private boolean a11yTabsWanted = true;\n"
        "    private static java.lang.ref.WeakReference<MainTabsActivity> a11yInstance;\n"
        "\n"
        "    public static void a11yRefreshTabs() {\n"
        "        final MainTabsActivity a = a11yInstance != null ? a11yInstance.get() : null;\n"
        "        if (a != null) {\n"
        "            a.a11yApplyTabs(true);\n"
        "        }\n"
        "    }\n"
        "\n"
        "    private void a11yApplyTabs(boolean animated) {\n"
        "        try {\n"
        "            animatorTabsVisible.setValue(a11yTabsWanted && !org.telegram.messenger.A11yConfig.getOldStyleMenu(), animated);\n"
        "            checkUi_tabsPosition(); // the value may already be right while the bar was not built yet\n"
        "            checkUi_fadeView();\n"
        "        } catch (Throwable e) {\n"
        "            org.telegram.messenger.FileLog.e(e);\n"
        "        }\n"
        "    }\n",
        "MainTabsActivity tabs-hidden state")
    _gate_once(
        mt,
        "        public void setTabsVisible(boolean visible) {\n"
        "            animatorTabsVisible.setValue(visible, true);\n"
        "        }\n",
        "        public void setTabsVisible(boolean visible) {\n"
        "            a11yTabsWanted = visible; // a11y-fork: remember what the screen asked for\n"
        "            animatorTabsVisible.setValue(visible && !org.telegram.messenger.A11yConfig.getOldStyleMenu(), true);\n"
        "        }\n",
        "MainTabsActivity setTabsVisible")
    _gate_once(
        mt,
        "        checkUnreadCount(true);\n"
        "\n"
        "        showAccountChangeHint();\n"
        "    }\n",
        "        checkUnreadCount(true);\n"
        "\n"
        "        showAccountChangeHint();\n"
        "        a11yInstance = new java.lang.ref.WeakReference<>(this); // a11y-fork: apply the old-style menu's tabs state\n"
        "        a11yApplyTabs(false);\n"
        "    }\n",
        "MainTabsActivity onResume tabs state")
    # Crash fix: DialogsActivity.createView asks setTabsVisible() while MainTabsActivity.createView is still
    # building its pages, i.e. before tabsView / tabsViewWrapper exist. Upstream never changes the animator's
    # value at that moment (it is already "visible"), so nothing runs; with the bar hidden by us the value
    # changes and checkUi_tabsPosition dereferenced null -> NullPointerException at start-up (Android 13 log).
    _gate_once(
        mt,
        "    private void checkUi_tabsPosition() {\n"
        "        final boolean isUpdateLayoutVisible = updateLayoutWrapper.isUpdateLayoutVisible();\n",
        "    private void checkUi_tabsPosition() {\n"
        "        if (tabsView == null || tabsViewWrapper == null || updateLayoutWrapper == null) {\n"
        "            return; // a11y-fork: can run before the bar is built (tabs hidden at start-up)\n"
        "        }\n"
        "        final boolean isUpdateLayoutVisible = updateLayoutWrapper.isUpdateLayoutVisible();\n",
        "MainTabsActivity tabs position null guard")


def patch_category_filter() -> None:
    """A category filter for the main chat list: All / Private chats / Groups / Channels / Bots.

    Accessible Settings switch "Chat category filter in the chat list" (A11yConfig.getCategoryFilter,
    default OFF). With it on, a button "Category: ..." sits in the top bar of the chat list; it opens
    a list of checkable items (All, Private chats, Groups, Channels, Bots). The choice (kept while
    the app runs, back to All when the switch is turned off) filters the main list and each of its
    folder tabs. The filter is applied in one place, DialogsActivity.getDialogsArray (the method every
    part of the list asks for its chats), so the adapter, the positions and the clicks all agree. Pickers
    (forward, share...), the archive and communities are never filtered. A secret chat counts as a private
    chat; a user whose account is a bot counts as a bot; a megagroup / forum counts as a group.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "    private ActionBarMenuItem a11yMenuItem; // a11y-fork: old-style main menu button (setting, default OFF)\n",
        "    private ActionBarMenuItem a11yMenuItem; // a11y-fork: old-style main menu button (setting, default OFF)\n"
        "    private ActionBarMenuItem a11yCategoryItem; // a11y-fork: category filter button (setting, default OFF)\n"
        "    private static java.lang.ref.WeakReference<DialogsActivity> a11yCategoryInstance;\n",
        "DialogsActivity category filter fields")
    _gate_once(
        da,
        "            a11yProxyItem.setOnClickListener(v -> presentFragment(new ProxyListActivity()));\n",
        "            a11yProxyItem.setOnClickListener(v -> presentFragment(new ProxyListActivity()));\n"
        "            a11yCategoryItem = menu.addItem(7, R.drawable.msg_folders); // a11y-fork: category filter button\n"
        "            a11yCategoryItem.setOnClickListener(v -> a11yShowCategoryMenu());\n"
        "            a11yCategoryInstance = new java.lang.ref.WeakReference<>(this);\n"
        "            a11yUpdateCategoryButton();\n",
        "DialogsActivity category filter button created")
    _gate_once(
        da,
        "        if (a11yMenuItem != null) { // a11y-fork: old-style main menu button\n",
        "        a11yUpdateCategoryButton(); // a11y-fork: category filter button\n"
        "        if (a11yMenuItem != null) { // a11y-fork: old-style main menu button\n",
        "DialogsActivity category filter refresh")
    _gate_once(
        da,
        "    public ArrayList<TLRPC.Dialog> getDialogsArray(int currentAccount, int dialogsType, int folderId, boolean frozen) {\n",
        "    public ArrayList<TLRPC.Dialog> getDialogsArray(int currentAccount, int dialogsType, int folderId, boolean frozen) {\n"
        "        final ArrayList<TLRPC.Dialog> a11yBase = a11yGetDialogsArrayBase(currentAccount, dialogsType, folderId, frozen);\n"
        "        // a11y-fork: category filter of the main chat list (setting, default OFF)\n"
        "        if (a11yBase == null || !org.telegram.messenger.A11yConfig.getCategoryFilter() || org.telegram.messenger.A11yConfig.categoryFilterValue == 0\n"
        "                || initialDialogsType != DIALOGS_TYPE_DEFAULT || onlySelect || folderId != 0 || communityId != 0\n"
        "                || !(dialogsType == DIALOGS_TYPE_DEFAULT || dialogsType == 7 || dialogsType == 8)) {\n"
        "            return a11yBase;\n"
        "        }\n"
        "        return a11yFilterByCategory(a11yBase, currentAccount);\n"
        "    }\n"
        "\n"
        "    private ArrayList<TLRPC.Dialog> a11yGetDialogsArrayBase(int currentAccount, int dialogsType, int folderId, boolean frozen) {\n",
        "DialogsActivity category filter in getDialogsArray")
    funcs = (
        "    // a11y-fork: category filter -- 0 all, 1 private chats, 2 groups, 3 channels, 4 bots, 5 unread, 6 read\n"
        "    private ArrayList<TLRPC.Dialog> a11yFilterByCategory(ArrayList<TLRPC.Dialog> base, int account) {\n"
        "        final int cat = org.telegram.messenger.A11yConfig.categoryFilterValue;\n"
        "        final ArrayList<TLRPC.Dialog> out = new ArrayList<>();\n"
        "        final MessagesController mc = MessagesController.getInstance(account);\n"
        "        for (int i = 0; i < base.size(); i++) {\n"
        "            final TLRPC.Dialog d = base.get(i);\n"
        "            if (d == null || d instanceof TLRPC.TL_dialogFolder) {\n"
        "                continue;\n"
        "            }\n"
        "            boolean match;\n"
        "            if (cat >= 5) {\n"
        "                final boolean isUnread = d.unread_count > 0 || d.unread_mark;\n"
        "                match = (cat == 5) == isUnread;\n"
        "            } else if (DialogObject.isEncryptedDialog(d.id)) {\n"
        "                match = cat == 1;\n"
        "            } else if (DialogObject.isUserDialog(d.id)) {\n"
        "                final TLRPC.User u = mc.getUser(d.id);\n"
        "                match = cat == (u != null && u.bot ? 4 : 1);\n"
        "            } else {\n"
        "                final TLRPC.Chat c = mc.getChat(-d.id);\n"
        "                if (c == null) {\n"
        "                    match = false;\n"
        "                } else if (ChatObject.isChannelAndNotMegaGroup(c)) {\n"
        "                    match = cat == 3;\n"
        "                } else {\n"
        "                    match = cat == 2;\n"
        "                }\n"
        "            }\n"
        "            if (match) {\n"
        "                out.add(d);\n"
        "            }\n"
        "        }\n"
        "        return out;\n"
        "    }\n"
        "\n"
        "    private String a11yCategoryName(int v) {\n"
        "        switch (v) {\n"
        "            case 1:\n"
        "                return getString(R.string.A11yCategoryPrivate);\n"
        "            case 2:\n"
        "                return getString(R.string.FilterGroups);\n"
        "            case 3:\n"
        "                return getString(R.string.FilterChannels);\n"
        "            case 4:\n"
        "                return getString(R.string.FilterBots);\n"
        "            case 5:\n"
        "                return getString(R.string.A11yCategoryUnread);\n"
        "            case 6:\n"
        "                return getString(R.string.A11yCategoryRead);\n"
        "            default:\n"
        "                return getString(R.string.FilterAllChats);\n"
        "        }\n"
        "    }\n"
        "\n"
        "    private void a11yUpdateCategoryButton() {\n"
        "        if (a11yCategoryItem == null) {\n"
        "            return;\n"
        "        }\n"
        "        a11yCategoryItem.setVisibility(org.telegram.messenger.A11yConfig.getCategoryFilter() ? View.VISIBLE : View.GONE);\n"
        "        a11yCategoryItem.setContentDescription(LocaleController.formatString(R.string.A11yCategoryButton, a11yCategoryName(org.telegram.messenger.A11yConfig.categoryFilterValue)));\n"
        "    }\n"
        "\n"
        "    private void a11yApplyCategory() {\n"
        "        try {\n"
        "            if (!org.telegram.messenger.A11yConfig.getCategoryFilter()) {\n"
        "                org.telegram.messenger.A11yConfig.categoryFilterValue = 0;\n"
        "            }\n"
        "            frozenDialogsList = null;\n"
        "            dialogsListFrozen = false;\n"
        "            if (viewPages != null) {\n"
        "                for (int i = 0; i < viewPages.length; i++) {\n"
        "                    if (viewPages[i] != null && viewPages[i].dialogsAdapter != null) {\n"
        "                        viewPages[i].dialogsAdapter.notifyDataSetChanged();\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "            a11yUpdateCategoryButton();\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n"
        "    }\n"
        "\n"
        "    public static void a11yRefreshCategory() {\n"
        "        final DialogsActivity a = a11yCategoryInstance != null ? a11yCategoryInstance.get() : null;\n"
        "        if (a != null) {\n"
        "            a.a11yApplyCategory();\n"
        "        }\n"
        "    }\n"
        "\n"
        "    private void a11ySetCategory(int v) {\n"
        "        org.telegram.messenger.A11yConfig.categoryFilterValue = v;\n"
        "        a11yApplyCategory();\n"
        "        if (fragmentView != null) {\n"
        "            fragmentView.announceForAccessibility(LocaleController.formatString(R.string.A11yCategoryShowing, a11yCategoryName(v)));\n"
        "        }\n"
        "    }\n"
        "\n"
        "    private void a11yShowCategoryMenu() {\n"
        "        try {\n"
        "            ItemOptions io = ItemOptions.makeOptions(this, a11yCategoryItem);\n"
        "            io.setColors(getThemedColor(Theme.key_actionBarDefaultTitle), getThemedColor(Theme.key_actionBarDefaultTitle));\n"
        "            io.setDimAlpha(0x08);\n"
        "            final int cur = org.telegram.messenger.A11yConfig.categoryFilterValue;\n"
        "            for (int v = 0; v <= 6; v++) {\n"
        "                final int value = v;\n"
        "                io.addChecked(cur == value, a11yCategoryName(value), () -> a11ySetCategory(value));\n"
        "            }\n"
        "            io.show();\n"
        "            io.setTranslationY(-dp(64));\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n"
        "    }\n"
        "\n"
        "    private void showItemOptions() {\n")
    _gate_once(da, "    private void showItemOptions() {\n", funcs, "DialogsActivity category filter functions")


# ---------------------------------------------------------------------------------------------
# Classic navigation drawer (Telegram release-11.4.2-5469) behind an Accessible Settings switch.
# The blob is a zip: java/... (LegacyDrawerLayoutContainer, LegacyDrawerHelper, Legacy* adapter and
# cells, SideMenultItemAnimator -- all taken from that release's git tag and adapted to the current
# source) and res/... (the few drawables the current Telegram no longer has).
# ---------------------------------------------------------------------------------------------
_LEGACY_DRAWER_BLOB = (
    "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"
    "v2r0lZoMB6QVEiRsnpwKJUi3J1FbfFAht65yxclM970X9b/gZTA+ESvudvpltwNK6d1jmDs2KW9LfXHGqqMc+/Jk1Zrjzn+HOOrM11laWnma8G"
    "3VqqbFW3yIzfh73+07mI5+GP/kUpC9Zs2riVOWVtA8csjhcxjEcinZRysj9YHLyxk9F9kefiVKXo1nZhhVlb6q4tN31uWpnGqFRpLLVSUWNfTr"
    "+lccd13uo5AgcFnQyULa502AjJbFbIvtQsL9TZt8hDxVommtul6fEuz61beVwucbewdrSESyW6Hfmw1TZx+4b00+tq7+yIWPRBqeuHUtf+7EWr"
    "Nwq9qd+xZvJj/l3rI7my/vz+CUyODJ6ufi7rnBKaAFBLAwQUAAAACACcoUVdHxJm81gCAABrAgAAJQAAAHJlcy9kcmF3YWJsZS14eGhkcGkvYm"
    "90dG9tX3NoYWRvdy5wbmfrDPBz5+WS4mJgYOD19HAJAtJCDAyMrBzMQNbNLe6fgJRBgE+Iq3uBz39SgIvdGyagXoGSIL9ghpntVRPzkticzMR4"
    "FML8tGb5ngwBWnLL08UxpOLW2x72piRDHmfX9wX/b6+TP1ch/PflXgVto/+ujuZ3v+hu/VhZdvpk7eJebjPZ678XHT727N81l48FydeeFRicPq"
    "g24fXci/8SpjXmSN7m3ifvJviwzkViUfPnBMsbl7UaXiWuWOew7Lvr8b28axf/vDdtYo6sZWZfRCWH3hVml9Nfzr0o2rKw9OBdwdPRKbtalZzc"
    "79S9nCWqE8XMOvOe7NsckfQrfm/XzdFdNkd3M88T5yvLH0kAJSRzyx9fnOZ7JWzdnJhV9013rZt3gUtQ9WOurv5Fp/dt53a4cypllXyPtHr9/+"
    "vcqbxGvt2zsxI+Sl6ODF21pLWryWe923IHdWn3nhOFJbNe3Gtft33B1rNbtn4TC5g4I7N7mqHrA20v7fJLW5QCmD3ert4tELkjyvm4YJVZ1NpC"
    "vbS1vw7EhK7eHXj7rkrSK7fCUzIBxyetii3XLKtbznXVdVvM+xaxTrG7Du1hSVEbL3uKrQrfuujpYs6FTy89mte+Tt/xc2sk37t8y5NhvltzMn"
    "5m2PXLrOFoPiW7SkRyebNSu5DudfEFT++k34rq6r6osOxz7X9XydB7tzd5bZ02c+e73J0ygV+uzb6Yw+EqdaVHxoltk6gxywk3P7msj/vslY4l"
    "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"
    "YXZhL29yZy90ZWxlZ3JhbS91aS9DZWxscy9MZWdhY3lEcmF3ZXJQcm9maWxlQ2VsbC5qYXZhUEsBAhQDFAAAAAgAFp9FXXN6j5NeCQAA0iIAAD"
    "QAAAAAAAAAAAAAAKSB2SwAAGphdmEvb3JnL3RlbGVncmFtL3VpL0NlbGxzL0xlZ2FjeURyYXdlclVzZXJDZWxsLmphdmFQSwECFAMUAAAACAAB"
    "n0VdRdnsxX8IAADIHQAANgAAAAAAAAAAAAAApIGJNgAAamF2YS9vcmcvdGVsZWdyYW0vdWkvQ2VsbHMvTGVnYWN5RHJhd2VyQWN0aW9uQ2VsbC"
    "5qYXZhUEsBAhQDFAAAAAgAAZ9FXWKDYaBkDAAAwTgAADwAAAAAAAAAAAAAAKSBXD8AAGphdmEvb3JnL3RlbGVncmFtL3VpL0FkYXB0ZXJzL0xl"
    "Z2FjeURyYXdlckxheW91dEFkYXB0ZXIuamF2YVBLAQIUAxQAAAAIABafRV1YmxnVfA4AANlEAAA/AAAAAAAAAAAAAACkgRpMAABqYXZhL29yZy"
    "90ZWxlZ3JhbS91aS9BY3Rpb25CYXIvTGVnYWN5RHJhd2VyTGF5b3V0Q29udGFpbmVyLmphdmFQSwECFAMUAAAACABVn0VdBU2cZgIOAADEXQAA"
    "OwAAAAAAAAAAAAAApIHzWgAAamF2YS9vcmcvdGVsZWdyYW0vdWkvQ29tcG9uZW50cy9TaWRlTWVudWx0SXRlbUFuaW1hdG9yLmphdmFQSwECFA"
    "MUAAAACACcoUVdS5AWy9oBAAAGAgAAJAAAAAAAAAAAAAAApIFOaQAAcmVzL2RyYXdhYmxlLWhkcGkvbXNnX3N0YXR1c19zZXQucG5nUEsBAhQD"
    "FAAAAAgAnKFFXTbAUBuaAQAAuAEAACMAAAAAAAAAAAAAAKSBamsAAHJlcy9kcmF3YWJsZS1oZHBpL2JvdHRvbV9zaGFkb3cucG5nUEsBAhQDFA"
    "AAAAgAnKFFXdzuboFfAAAAcwAAACEAAAAAAAAAAAAAAKSBRW0AAHJlcy9kcmF3YWJsZS1oZHBpL21lbnVfc2hhZG93LnBuZ1BLAQIUAxQAAAAI"
    "AJyhRV21rS455gEAABYCAAAlAAAAAAAAAAAAAACkgeNtAAByZXMvZHJhd2FibGUtaGRwaS9tc2dfc3RhdHVzX2VkaXQucG5nUEsBAhQDFAAAAA"
    "gAnKFFXcTogz51AQAAnAEAACAAAAAAAAAAAAAAAKSBDHAAAHJlcy9kcmF3YWJsZS1oZHBpL21zZ19pbnZpdGUucG5nUEsBAhQDFAAAAAgAnKFF"
    "XQB9bos7AgAAWgIAACUAAAAAAAAAAAAAAKSBv3EAAHJlcy9kcmF3YWJsZS14aGRwaS9tc2dfc3RhdHVzX3NldC5wbmdQSwECFAMUAAAACACcoU"
    "Vd4rYAYpkBAAC2AQAAJAAAAAAAAAAAAAAApIE9dAAAcmVzL2RyYXdhYmxlLXhoZHBpL2JvdHRvbV9zaGFkb3cucG5nUEsBAhQDFAAAAAgAnKFF"
    "XUM2lc1MAAAAUAAAACIAAAAAAAAAAAAAAKSBGHYAAHJlcy9kcmF3YWJsZS14aGRwaS9tZW51X3NoYWRvdy5wbmdQSwECFAMUAAAACACcoUVd6k"
    "kf+EsCAABpAgAAJgAAAAAAAAAAAAAApIGkdgAAcmVzL2RyYXdhYmxlLXhoZHBpL21zZ19zdGF0dXNfZWRpdC5wbmdQSwECFAMUAAAACACcoUVd"
    "0GR9pqoBAADJAQAAIQAAAAAAAAAAAAAApIEzeQAAcmVzL2RyYXdhYmxlLXhoZHBpL21zZ19pbnZpdGUucG5nUEsBAhQDFAAAAAgAnKFFXbhqGp"
    "9BAQAAegEAACQAAAAAAAAAAAAAAKSBHHsAAHJlcy9kcmF3YWJsZS1tZHBpL21zZ19zdGF0dXNfc2V0LnBuZ1BLAQIUAxQAAAAIAJyhRV023LGS"
    "1wAAANQAAAAjAAAAAAAAAAAAAACkgZ98AAByZXMvZHJhd2FibGUtbWRwaS9ib3R0b21fc2hhZG93LnBuZ1BLAQIUAxQAAAAIAJyhRV3mb1m1Rg"
    "AAAEsAAAAhAAAAAAAAAAAAAACkgbd9AAByZXMvZHJhd2FibGUtbWRwaS9tZW51X3NoYWRvdy5wbmdQSwECFAMUAAAACACcoUVda3a3oEkBAACA"
    "AQAAJQAAAAAAAAAAAAAApIE8fgAAcmVzL2RyYXdhYmxlLW1kcGkvbXNnX3N0YXR1c19lZGl0LnBuZ1BLAQIUAxQAAAAIAJyhRV0C0uWyDgEAAD"
    "4BAAAgAAAAAAAAAAAAAACkgch/AAByZXMvZHJhd2FibGUtbWRwaS9tc2dfaW52aXRlLnBuZ1BLAQIUAxQAAAAIAJyhRV2+s+Qj6AIAAP4CAAAm"
    "AAAAAAAAAAAAAACkgRSBAAByZXMvZHJhd2FibGUteHhoZHBpL21zZ19zdGF0dXNfc2V0LnBuZ1BLAQIUAxQAAAAIAJyhRV0fEmbzWAIAAGsCAA"
    "AlAAAAAAAAAAAAAACkgUCEAAByZXMvZHJhd2FibGUteHhoZHBpL2JvdHRvbV9zaGFkb3cucG5nUEsBAhQDFAAAAAgAnKFFXaRfW3xNAAAAUgAA"
    "ACMAAAAAAAAAAAAAAKSB24YAAHJlcy9kcmF3YWJsZS14eGhkcGkvbWVudV9zaGFkb3cucG5nUEsBAhQDFAAAAAgAnKFFXXtTErUMAwAAHwMAAC"
    "cAAAAAAAAAAAAAAKSBaYcAAHJlcy9kcmF3YWJsZS14eGhkcGkvbXNnX3N0YXR1c19lZGl0LnBuZ1BLAQIUAxQAAAAIAJyhRV2JDT1N6AEAAP0B"
    "AAAiAAAAAAAAAAAAAACkgbqKAAByZXMvZHJhd2FibGUteHhoZHBpL21zZ19pbnZpdGUucG5nUEsFBgAAAAAcABwAgQkAAOKMAAAAAA=="
)


def patch_legacy_navigation_drawer() -> None:
    """Real classic navigation drawer, selectable from Accessible Settings (default OFF = current Telegram).

    "Use legacy navigation drawer" (A11yConfig.useLegacyNavigationDrawer, read when the main screen is
    created, so the app must be reopened after changing it). With it on, LaunchActivity creates a
    LegacyDrawerLayoutContainer (the current container plus the classic side panel, swipe gesture, scrim,
    shadow and open/close) and LegacyDrawerHelper builds the classic side menu from the original adapter and
    cells. It opens by swiping from the left edge of the chat list, or with the classic hamburger button at the
    top-left of the chat list's top bar. Back closes it. Off: nothing of this is created.
    """
    import base64
    import io
    import zipfile

    data = base64.b64decode("".join(_LEGACY_DRAWER_BLOB))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as e:  # pragma: no cover
        print("WARN: legacy drawer blob unreadable: %s" % e)
        return
    count = 0
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        if name.startswith("java/"):
            dst = JAVA / name[len("java/"):]
        elif name.startswith("res/"):
            dst = RES / name[len("res/"):]
        else:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(zf.read(name))
        count += 1
    print("Legacy drawer: %d files installed OK" % count)

    # a11y-fork: bring "New Channel" back into the classic drawer (right after New Group, as in 11.4.2)
    _gate_once(
        JAVA / "org/telegram/ui/Adapters/LegacyDrawerLayoutAdapter.java",
        "        //items.add(new Item(4, LocaleController.getString(R.string.NewChannel), newChannelIcon));\n",
        "        items.add(new Item(4, LocaleController.getString(R.string.NewChannel), newChannelIcon)); // a11y-fork: New Channel restored\n",
        "Legacy drawer New Channel item")
    _gate_once(
        JAVA / "org/telegram/ui/Adapters/LegacyDrawerLayoutAdapter.java",
        "        newGroupIcon = R.drawable.msg_groups;\n",
        "        newGroupIcon = R.drawable.msg_groups;\n        newChannelIcon = R.drawable.msg_channel; // a11y-fork\n",
        "Legacy drawer New Channel icon")
    _gate_once(
        JAVA / "org/telegram/ui/LegacyDrawerHelper.java",
        "            } else if (id == 3) {\n",
        "            } else if (id == 4) { // a11y-fork: New Channel\n"
        "                Bundle args = new Bundle();\n"
        "                args.putInt(\"step\", 0);\n"
        "                activity.presentFragment(new ChannelCreateActivity(args));\n"
        "                container.closeDrawer(false);\n"
        "            } else if (id == 3) {\n",
        "Legacy drawer New Channel click")

    la = JAVA / "org/telegram/ui/LaunchActivity.java"
    _gate_once(
        la,
        "        drawerLayoutContainer = new DrawerLayoutContainer(this);\n",
        "        org.telegram.messenger.A11yConfig.loadLegacyNavigationDrawer(); // a11y-fork: classic drawer switch\n"
        "        drawerLayoutContainer = org.telegram.messenger.A11yConfig.useLegacyNavigationDrawer\n"
        "                ? new org.telegram.ui.ActionBar.LegacyDrawerLayoutContainer(this)\n"
        "                : new DrawerLayoutContainer(this);\n",
        "LaunchActivity legacy drawer container")
    _gate_once(
        la,
        "        drawerLayoutContainer.setParentActionBarLayout(actionBarLayout);\n",
        "        drawerLayoutContainer.setParentActionBarLayout(actionBarLayout);\n"
        "        org.telegram.ui.LegacyDrawerHelper.setup(this, drawerLayoutContainer); // a11y-fork: builds the classic side menu when the switch is on\n",
        "LaunchActivity legacy drawer setup")
    _gate_once(
        la,
        "    public boolean onBackPressed(boolean invoked) {\n"
        "        if (FloatingDebugController.onBackPressed(invoked)) {\n"
        "            return false;\n"
        "        }\n",
        "    public boolean onBackPressed(boolean invoked) {\n"
        "        if (FloatingDebugController.onBackPressed(invoked)) {\n"
        "            return false;\n"
        "        }\n"
        "        if (org.telegram.ui.LegacyDrawerHelper.isOpen()) { // a11y-fork: Back closes the classic drawer\n"
        "            if (invoked) {\n"
        "                org.telegram.ui.LegacyDrawerHelper.closeIfOpen();\n"
        "            }\n"
        "            return false;\n"
        "        }\n",
        "LaunchActivity legacy drawer back")

    # The classic hamburger: top-left of the chat list's top bar (it was the bar's back button).
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "            if (searchString != null || folderId != 0 || communityId != 0) {\n"
        "                actionBar.setBackButtonDrawable(backDrawable = new BackDrawable(false));\n"
        "            }\n",
        "            if (searchString != null || folderId != 0 || communityId != 0) {\n"
        "                actionBar.setBackButtonDrawable(backDrawable = new BackDrawable(false));\n"
        "            } else if (org.telegram.ui.LegacyDrawerHelper.isActive()) { // a11y-fork: classic hamburger, top-left\n"
        "                org.telegram.ui.ActionBar.MenuDrawable a11yMenuDrawable = new org.telegram.ui.ActionBar.MenuDrawable();\n"
        "                a11yMenuDrawable.setRoundCap();\n"
        "                actionBar.setBackButtonDrawable(a11yMenuDrawable);\n"
        "                actionBar.setBackButtonContentDescription(getString(R.string.AccDescrOpenMenu));\n"
        "            }\n",
        "DialogsActivity legacy hamburger button")
    _gate_once(
        da,
        "                    } else if (onlySelect || folderId != 0 || communityId != 0) {\n"
        "                        finishFragment();\n"
        "                    }\n"
        "                } else if (id == 1) {\n",
        "                    } else if (onlySelect || folderId != 0 || communityId != 0) {\n"
        "                        finishFragment();\n"
        "                    } else if (org.telegram.ui.LegacyDrawerHelper.isActive()) { // a11y-fork: hamburger opens the classic drawer\n"
        "                        org.telegram.ui.LegacyDrawerHelper.open();\n"
        "                    }\n"
        "                } else if (id == 1) {\n",
        "DialogsActivity legacy hamburger click")


def patch_old_menu_hides_options() -> None:
    """With the old-style main menu on, the top-right "More options" button of the new menu is gone.

    The button's visibility is one function, DialogsActivity.checkUi_itemOptionsVisibility (an
    animated factor; searching, sliding and the done button already hide it through it). The old-style
    menu being on is one more reason for a factor of 0 there. The function is also run whenever the
    chat list refreshes its top bar and right when the switch is flipped, so the button goes or comes
    at once. Things that live only in that popup (switching the theme, the bots of the side menu, the
    proxy entry) are not in the old-style menu; the proxy has its own switch for a button of the top bar.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "        final float factor = factor1 * factor2 * factor3;\n"
        "        FragmentFloatingButton.setAnimatedVisibility(optionsItem, factor);\n",
        "        final float factor = org.telegram.messenger.A11yConfig.getOldStyleMenu() ? 0f : factor1 * factor2 * factor3; // a11y-fork: hidden while the old-style menu is on\n"
        "        FragmentFloatingButton.setAnimatedVisibility(optionsItem, factor);\n",
        "DialogsActivity options button hidden by old-style menu")
    _gate_once(
        da,
        "        a11yCategoryItem.setContentDescription(LocaleController.formatString(R.string.A11yCategoryButton, a11yCategoryName(org.telegram.messenger.A11yConfig.categoryFilterValue)));\n"
        "    }\n",
        "        a11yCategoryItem.setContentDescription(LocaleController.formatString(R.string.A11yCategoryButton, a11yCategoryName(org.telegram.messenger.A11yConfig.categoryFilterValue)));\n"
        "        // a11y-fork: the top bar follows the old-style menu switch (its button in, More options out)\n"
        "        if (a11yMenuItem != null) {\n"
        "            a11yMenuItem.setVisibility((org.telegram.messenger.A11yConfig.getOldStyleMenu() && !org.telegram.ui.LegacyDrawerHelper.isActive()) ? View.VISIBLE : View.GONE);\n"
        "        }\n"
        "        try {\n"
        "            checkUi_itemOptionsVisibility();\n"
        "        } catch (Throwable ignore) {\n"
        "        }\n"
        "    }\n",
        "DialogsActivity top bar follows old-style menu switch")


def patch_old_menu_extras() -> None:
    """Theme switch and the bots of the side menu in the old-style main menu (the proxy is not here: it has its own top bar button).

    With the old-style menu on, the new "More options" button is hidden, and these two lived only in
    its popup. They are copied from that popup's own code as the generated file has it (so they act
    exactly as there, even if the popup changes) and put where the 11.4.2 drawer had them: the day / night
    switch first (it was the button of the drawer's header), the bots right after My Profile. The proxy entry is
    left out on purpose: it is the proxy button of the top bar (its own Accessible Settings switch), which
    comes right after the Main menu button.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    t = da.read_text(encoding="utf-8")
    th_start = "        final boolean isCurrentThemeDark;\n        if (resourceProvider != null) {\n"
    th_end = "        io.addGap();\n        io.add(R.drawable.outline_groups_24, getString(R.string.NewGroup)"
    bt_start = "        TLRPC.TL_attachMenuBots menuBots = MediaDataController.getInstance(UserConfig.selectedAccount).getAttachMenuBots();\n"
    bt_end = "        if (getUserConfig().showCallsTab) {\n"
    for name, marker in (("theme start", th_start), ("theme end", th_end), ("bots start", bt_start), ("bots end", bt_end)):
        if t.count(marker) != 1:
            print("WARN: old-style menu extras: %s marker found %d times" % (name, t.count(marker)))
            return
    a = t.index(th_start)
    b = t.index(th_end, a)
    c = t.index(bt_start, b)
    d = t.index(bt_end, c)
    theme_block = t[a:b]
    bots_block = t[c:d]
    if "io.add(" not in theme_block or "addBot" not in bots_block:
        print("WARN: old-style menu extras: extracted blocks look wrong")
        return
    launch_decl = (
        "        final Activity a11yAct = getParentActivity();\n"
        "        final LaunchActivity launchActivity = a11yAct instanceof LaunchActivity ? (LaunchActivity) a11yAct : null;\n")
    a_anchor = ("            io.setDimAlpha(0x08);\n"
                "            io.add(R.drawable.msg_openprofile, getString(R.string.MyProfile), () -> {\n")
    b_anchor = ("                presentFragment(new ProfileActivity(args, null));\n"
                "            });\n")
    # first: the day / night switch (in the old drawer it was the button of the header, the first thing)
    _gate_once(da, a_anchor,
               "            // a11y-fork: the day / night switch comes first, as the old drawer's header button did\n"
               + theme_block + a_anchor,
               "DialogsActivity old-style menu theme switch first")
    # then, after My Profile: the bots of the side menu (the old drawer listed them right there)
    _gate_once(da, b_anchor,
               b_anchor + "            // a11y-fork: the side-menu bots, right after My Profile as in the old drawer\n"
               + launch_decl + bots_block,
               "DialogsActivity old-style menu bots after My Profile")


def patch_message_tap_sound() -> None:
    """The same optional system click for a tap on a message (setting "Touch sound", default OFF).

    With TalkBack, a double tap reaches a message as ACTION_CLICK, which ChatMessageCell handles by
    itself -- nothing on that path ever asks the system to play its touch sound, so a message
    stayed silent where every ordinary button of the phone clicks. The click is played first thing
    on that tap, before the tap's own work starts, both for the message itself and for the parts
    inside it TalkBack lists on their own (links, buttons, the avatar, rich blocks). It is the
    same switch and the same A11yConfig.playChatOpenSound() as the chat-open sound, so the system's
    own "Touch sounds" setting still decides whether anything is heard.
    """
    cmc = JAVA / "org/telegram/ui/Cells/ChatMessageCell.java"
    _gate_once(
        cmc,
        "    public boolean performAccessibilityAction(int action, Bundle arguments) {\n",
        "    public boolean performAccessibilityAction(int action, Bundle arguments) {\n"
        "        if (action == AccessibilityNodeInfo.ACTION_CLICK) { // a11y-fork: touch sound for a tap on a message\n"
        "            org.telegram.messenger.A11yConfig.playChatOpenSound();\n"
        "        }\n",
        "ChatMessageCell tap sound (message)")
    _gate_once(
        cmc,
        "                } else if (action == AccessibilityNodeInfo.ACTION_CLICK) {\n"
        "                    if (virtualViewId == PROFILE) {\n",
        "                } else if (action == AccessibilityNodeInfo.ACTION_CLICK) {\n"
        "                    org.telegram.messenger.A11yConfig.playChatOpenSound(); // a11y-fork: touch sound for a tap on a part of a message\n"
        "                    if (virtualViewId == PROFILE) {\n",
        "ChatMessageCell tap sound (parts of a message)")


def patch_voice_share() -> None:
    """Share for a downloaded voice message, at the place every other media gets its Share.

    Telegram files a voice message under message type 2, which never reaches the block that adds
    Save to downloads / Share (that block is for type 4: downloaded photos, video, music and files).
    The same OPTION_SHARE handler works for a voice message (it only needs the document and the
    local file), so the item is added at the start of the same place in the menu, only when the
    voice file is really on the phone (same rule as for the other media) and Telegram allows
    saving/forwarding it.
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    _gate_once(
        ca,
        "                if (type == 2) {\n"
        "                    if (chatMode != MODE_SCHEDULED) {\n",
        "                // a11y-fork: Save to music + Share for a downloaded voice message (setting, default OFF)\n"
        "                if (type == 2 && org.telegram.messenger.A11yConfig.getVoiceShareSave() && selectedObject.isVoice() && !noforwardsOrPaidMedia && !selectedObject.isVoiceOnce() && !selectedObject.isRoundOnce() && selectedObject.getDocument() != null && a11yMessageFileExists(selectedObject)) {\n"
        "                    items.add(LocaleController.getString(R.string.SaveToMusic));\n"
        "                    options.add(212);\n"
        "                    icons.add(R.drawable.msg_download);\n"
        "                    items.add(LocaleController.getString(R.string.ShareFile));\n"
        "                    options.add(OPTION_SHARE);\n"
        "                    icons.add(R.drawable.msg_shareout);\n"
        "                }\n"
        "                if (type == 2) {\n"
        "                    if (chatMode != MODE_SCHEDULED) {\n",
        "ChatActivity voice message Share")
    _gate_once(
        ca,
        "    private boolean showWelcomeMessageRevertOption(MessageObject messageObject) {\n",
        "    // a11y-fork: is the file of this message on the phone (the rule getMessageType uses for type 4)\n"
        "    private boolean a11yMessageFileExists(MessageObject m) {\n"
        "        try {\n"
        "            String p = m.messageOwner != null ? m.messageOwner.attachPath : null;\n"
        "            if (!TextUtils.isEmpty(p) && new File(p).exists()) {\n"
        "                return true;\n"
        "            }\n"
        "            return m.mediaExists;\n"
        "        } catch (Throwable e) {\n"
        "            return false;\n"
        "        }\n"
        "    }\n\n"
        "    private boolean showWelcomeMessageRevertOption(MessageObject messageObject) {\n",
        "ChatActivity voice file-exists helper")

    _gate_once(
        ca,
        "            case OPTION_LEAVE_COMMENT: { // a11y-fork: leave comment handler\n",
        "            case 212: { // a11y-fork: save a voice message to the phone's music\n"
        "                try {\n"
        "                    if (Build.VERSION.SDK_INT >= 23 && (Build.VERSION.SDK_INT <= 28 || BuildVars.NO_SCOPED_STORAGE) && getParentActivity().checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {\n"
        "                        getParentActivity().requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, 4);\n"
        "                        selectedObject = null;\n"
        "                        selectedObjectGroup = null;\n"
        "                        selectedObjectToEditCaption = null;\n"
        "                        return;\n"
        "                    }\n"
        "                    final MessageObject a11yVoice = selectedObject;\n"
        "                    String a11yPath = a11yVoice.messageOwner != null ? a11yVoice.messageOwner.attachPath : null;\n"
        "                    if (TextUtils.isEmpty(a11yPath) || !new File(a11yPath).exists()) {\n"
        "                        a11yPath = FileLoader.getInstance(currentAccount).getPathToMessage(a11yVoice.messageOwner).toString();\n"
        "                    }\n"
        "                    if (!TextUtils.isEmpty(a11yPath) && new File(a11yPath).exists()) {\n"
        "                        MediaController.saveFile(a11yPath, getParentActivity(), 3, null, a11yVoice.getDocument() != null ? a11yVoice.getDocument().mime_type : \"audio/ogg\", uri -> AndroidUtilities.runOnUIThread(() -> {\n"
        "                            if (uri != null && getParentActivity() != null && fragmentView != null) {\n"
        "                                BulletinFactory.of(ChatActivity.this).createDownloadBulletin(BulletinFactory.FileType.AUDIOS, 1, themeDelegate).show();\n"
        "                            }\n"
        "                        }));\n"
        "                    }\n"
        "                } catch (Throwable e) {\n"
        "                    FileLog.e(e);\n"
        "                }\n"
        "                selectedObject = null;\n"
        "                selectedObjectToEditCaption = null;\n"
        "                selectedObjectGroup = null;\n"
        "                break;\n"
        "            }\n"
        "            case OPTION_LEAVE_COMMENT: { // a11y-fork: leave comment handler\n",
        "ChatActivity voice save-to-music handler")


def patch_player_seek_buttons() -> None:
    """Rewind / Forward 10 seconds in the audio player bar (music and voice), beside Close.

    The bar on top of the chat list and of a chat (FragmentContextView, style audio player) gets
    two small buttons to the left of the speed button, only when the Accessible Settings switch
    "Rewind and forward in the audio player" (A11yConfig.getPlayerSeekButtons) is on; default OFF.
    Each press moves the playing file 10 seconds, clamped to the file. The buttons are created with
    the bar, shown when the bar shows an audio player, and the title leaves room for them.
    """
    fcv = JAVA / "org/telegram/ui/Components/FragmentContextView.java"
    _gate_once(
        fcv,
        "    private ImageView closeButton;\n",
        "    private ImageView closeButton;\n"
        "    private TextView a11yRewindButton, a11yForwardButton; // a11y-fork: rewind / forward 10 s (setting, default OFF)\n",
        "FragmentContextView seek button fields")
    _gate_once(
        fcv,
        "        addView(closeButton, LayoutHelper.createFrame(36, 36, Gravity.RIGHT | Gravity.TOP, 0, 0, 4, 0));\n",
        "        addView(closeButton, LayoutHelper.createFrame(36, 36, Gravity.RIGHT | Gravity.TOP, 0, 0, 4, 0));\n"
        "        // a11y-fork: optional Rewind / Forward 10 s beside Close (left of the speed button)\n"
        "        a11yRewindButton = a11yCreateSeekButton(context, \"\\u2039 10\", R.string.A11yPlayerRewind, -10000);\n"
        "        a11yForwardButton = a11yCreateSeekButton(context, \"10 \\u203a\", R.string.A11yPlayerForward, 10000);\n"
        "        addView(a11yForwardButton, LayoutHelper.createFrame(44, 36, Gravity.RIGHT | Gravity.TOP, 0, 0, 72, 0));\n"
        "        addView(a11yRewindButton, LayoutHelper.createFrame(44, 36, Gravity.RIGHT | Gravity.TOP, 0, 0, 116, 0));\n",
        "FragmentContextView seek buttons created")
    _gate_once(
        fcv,
        "        currentStyle = style;\n"
        "        frameLayout.setWillNotDraw(currentStyle != STYLE_INACTIVE_GROUP_CALL);\n",
        "        currentStyle = style;\n"
        "        a11yUpdateSeekButtons(style == STYLE_AUDIO_PLAYER); // a11y-fork: rewind / forward visibility\n"
        "        frameLayout.setWillNotDraw(currentStyle != STYLE_INACTIVE_GROUP_CALL);\n",
        "FragmentContextView seek buttons visibility")
    _gate_once(
        fcv,
        "                titleTextView.setLayoutParams(LayoutHelper.createFrame(LayoutHelper.MATCH_PARENT, 36, Gravity.LEFT | Gravity.TOP, 37, 0, (isSideMenued ? 64 : 0) + 36, 0));\n",
        "                titleTextView.setLayoutParams(LayoutHelper.createFrame(LayoutHelper.MATCH_PARENT, 36, Gravity.LEFT | Gravity.TOP, 37, 0, (isSideMenued ? 64 : 0) + 36 + a11yPlayerSeekExtra(), 0)); // a11y-fork: room for rewind / forward\n",
        "FragmentContextView title room for seek buttons")
    _gate_once(
        fcv,
        "    private void updateStyle(@Style int style) {\n"
        "        updateStyle(style, false);\n"
        "    }\n",
        "    private void updateStyle(@Style int style) {\n"
        "        updateStyle(style, false);\n"
        "    }\n\n"
        "    // a11y-fork: Rewind / Forward 10 s buttons of the audio player bar\n"
        "    private TextView a11yCreateSeekButton(Context context, String label, int descRes, final int deltaMs) {\n"
        "        TextView b = new TextView(context);\n"
        "        b.setText(label);\n"
        "        b.setGravity(Gravity.CENTER);\n"
        "        b.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13);\n"
        "        b.setTypeface(AndroidUtilities.bold());\n"
        "        b.setTextColor(getThemedColor(Theme.key_inappPlayerClose));\n"
        "        b.setBackground(Theme.createSelectorDrawable(getThemedColor(Theme.key_inappPlayerClose) & 0x19ffffff, 1, dp(14)));\n"
        "        b.setContentDescription(getString(descRes));\n"
        "        b.setVisibility(GONE);\n"
        "        b.setOnClickListener(v -> a11ySeekBy(deltaMs));\n"
        "        return b;\n"
        "    }\n\n"
        "    private int a11yPlayerSeekExtra() {\n"
        "        return org.telegram.messenger.A11yConfig.getPlayerSeekButtons() ? 124 : 0;\n"
        "    }\n\n"
        "    private void a11yUpdateSeekButtons(boolean audioStyle) {\n"
        "        final int vis = audioStyle && org.telegram.messenger.A11yConfig.getPlayerSeekButtons() ? VISIBLE : GONE;\n"
        "        if (a11yRewindButton != null) {\n"
        "            a11yRewindButton.setVisibility(vis);\n"
        "        }\n"
        "        if (a11yForwardButton != null) {\n"
        "            a11yForwardButton.setVisibility(vis);\n"
        "        }\n"
        "    }\n\n"
        "    private void a11ySeekBy(int deltaMs) {\n"
        "        try {\n"
        "            final MessageObject m = MediaController.getInstance().getPlayingMessageObject();\n"
        "            if (m == null) {\n"
        "                return;\n"
        "            }\n"
        "            final long cur = MediaController.getInstance().getProgressMs(m);\n"
        "            if (cur < 0) {\n"
        "                return;\n"
        "            }\n"
        "            long target = Math.max(0, cur + deltaMs);\n"
        "            final long dur = MediaController.getInstance().getDuration();\n"
        "            if (dur > 0) {\n"
        "                target = Math.min(target, Math.max(0, dur - 300));\n"
        "            }\n"
        "            MediaController.getInstance().seekToProgressMs(m, target);\n"
        "        } catch (Throwable e) {\n"
        "            org.telegram.messenger.FileLog.e(e);\n"
        "        }\n"
        "    }\n",
        "FragmentContextView seek helpers")


def patch_sender_options_menu() -> None:
    """The \"Sender options\" of the fork (the menu held on a sender's avatar: profile, private chat,
    mention, search their messages) as items of Message options.

    Accessible Settings switch \"Sender options in message menu\" (A11yConfig.getSenderOptionsInMenu),
    default OFF. With it on, a message from someone else in a group adds, just before \"Select\"
    (which stays last): Open profile, Send message, Mention, Search messages -- or for a message
    sent as a channel / group: Open profile, Open channel/group, Mention, Search messages.
    Every item calls the same code the avatar menu calls, so both ways do the same thing.
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    menu_block = (
        "        // a11y-fork: sender options in the message menu (setting, default OFF)\n"
        "        try {\n"
        "            if (org.telegram.messenger.A11yConfig.getSenderOptionsInMenu() && message != null && a11yCanShowSenderOptions(message)) {\n"
        "                final long a11yFromId = message.getFromChatId();\n"
        "                final boolean a11yMentionOk = currentChat != null && (bottomChannelButtonsLayout == null || bottomChannelButtonsLayout.getVisibility() != View.VISIBLE) && (bottomOverlay == null || bottomOverlay.getVisibility() != View.VISIBLE);\n"
        "                final boolean a11ySearchOk = currentChat != null && (threadMessageId == 0 || isTopic) && (!ChatObject.isChannel(currentChat) || currentChat.megagroup);\n"
        "                if (a11yFromId > 0) {\n"
        "                    items.add(LocaleController.getString(R.string.OpenProfile));\n"
        "                    options.add(207);\n"
        "                    icons.add(R.drawable.msg_openprofile);\n"
        "                    items.add(LocaleController.getString(R.string.SendMessage));\n"
        "                    options.add(208);\n"
        "                    icons.add(R.drawable.msg_discussion);\n"
        "                    if (a11yMentionOk) {\n"
        "                        items.add(LocaleController.getString(R.string.Mention));\n"
        "                        options.add(209);\n"
        "                        icons.add(R.drawable.msg_mention);\n"
        "                    }\n"
        "                    if (a11ySearchOk) {\n"
        "                        items.add(LocaleController.getString(R.string.AvatarPreviewSearchMessages));\n"
        "                        options.add(210);\n"
        "                        icons.add(R.drawable.msg_search);\n"
        "                    }\n"
        "                } else if (a11yFromId < 0) {\n"
        "                    final TLRPC.Chat a11yFromChat = getMessagesController().getChat(-a11yFromId);\n"
        "                    if (a11yFromChat != null) {\n"
        "                        items.add(LocaleController.getString(R.string.OpenProfile));\n"
        "                        options.add(207);\n"
        "                        icons.add(R.drawable.msg_openprofile);\n"
        "                        if (currentChat == null || currentChat.id != a11yFromChat.id || isThreadChat()) {\n"
        "                            items.add(LocaleController.getString(a11yFromChat.broadcast ? R.string.OpenChannel2 : R.string.OpenGroup2));\n"
        "                            options.add(211);\n"
        "                            icons.add(a11yFromChat.broadcast ? R.drawable.msg_channel : R.drawable.msg_discussion);\n"
        "                        }\n"
        "                        if (a11yMentionOk && !TextUtils.isEmpty(ChatObject.getPublicUsername(a11yFromChat))) {\n"
        "                            items.add(LocaleController.getString(R.string.Mention));\n"
        "                            options.add(209);\n"
        "                            icons.add(R.drawable.msg_mention);\n"
        "                        }\n"
        "                        if (a11ySearchOk) {\n"
        "                            items.add(LocaleController.getString(R.string.AvatarPreviewSearchMessages));\n"
        "                            options.add(210);\n"
        "                            icons.add(R.drawable.msg_search);\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n\n")
    select_anchor = "        // a11y-fork: OPTION_SELECT_MESSAGE menu\n"
    _gate_once(ca, select_anchor, menu_block + select_anchor, "ChatActivity sender options menu items")

    helper_anchor = "    private boolean showWelcomeMessageRevertOption(MessageObject messageObject) {\n"
    helper = (
        "    // a11y-fork: the avatar menu of a sender exists for a message of someone else in a group\n"
        "    private boolean a11yCanShowSenderOptions(MessageObject m) {\n"
        "        return currentChat != null && (!ChatObject.isChannel(currentChat) || currentChat.megagroup)\n"
        "                && chatMode != MODE_SCHEDULED && !isInsideContainer\n"
        "                && m.messageOwner != null && m.messageOwner.from_id != null && m.contentType == 0\n"
        "                && !m.isOutOwner() && !m.isSponsored() && !m.isEphemeral();\n"
        "    }\n\n")
    _gate_once(ca, helper_anchor, helper + helper_anchor, "ChatActivity sender options helper")

    handler_anchor = "            case OPTION_LEAVE_COMMENT: { // a11y-fork: leave comment handler\n"
    handler = (
        "            case 207:\n"
        "            case 208:\n"
        "            case 209:\n"
        "            case 210:\n"
        "            case 211: { // a11y-fork: sender options in the message menu\n"
        "                try {\n"
        "                    final MessageObject a11yMsg = selectedObject;\n"
        "                    final long a11yFrom = a11yMsg != null ? a11yMsg.getFromChatId() : 0;\n"
        "                    final ChatMessageCellDelegate a11yDelegate = getChatMessageCellDelegate();\n"
        "                    if (a11yFrom > 0) {\n"
        "                        final TLRPC.User a11yUser = getMessagesController().getUser(a11yFrom);\n"
        "                        if (a11yUser != null) {\n"
        "                            if (option == 207) {\n"
        "                                a11yDelegate.openProfile(a11yUser);\n"
        "                            } else if (option == 208) {\n"
        "                                Bundle a11yArgs = new Bundle();\n"
        "                                a11yArgs.putLong(\"user_id\", a11yUser.id);\n"
        "                                if (getMessagesController().checkCanOpenChat(a11yArgs, ChatActivity.this, a11yMsg)) {\n"
        "                                    presentFragment(new ChatActivity(a11yArgs));\n"
        "                                }\n"
        "                            } else if (option == 209) {\n"
        "                                a11yDelegate.appendMention(a11yUser);\n"
        "                            } else if (option == 210) {\n"
        "                                openSearchWithUser(a11yUser);\n"
        "                            }\n"
        "                        }\n"
        "                    } else if (a11yFrom < 0) {\n"
        "                        final TLRPC.Chat a11yChat = getMessagesController().getChat(-a11yFrom);\n"
        "                        if (a11yChat != null) {\n"
        "                            if (option == 207) {\n"
        "                                a11yDelegate.openProfile(a11yChat);\n"
        "                            } else if (option == 211) {\n"
        "                                Bundle a11yArgs = new Bundle();\n"
        "                                a11yArgs.putLong(\"chat_id\", a11yChat.id);\n"
        "                                if (getMessagesController().checkCanOpenChat(a11yArgs, ChatActivity.this, a11yMsg)) {\n"
        "                                    presentFragment(new ChatActivity(a11yArgs));\n"
        "                                }\n"
        "                            } else if (option == 209) {\n"
        "                                a11yDelegate.appendMention(a11yChat);\n"
        "                            } else if (option == 210) {\n"
        "                                openSearchWithChat(a11yChat);\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                } catch (Throwable e) {\n"
        "                    FileLog.e(e);\n"
        "                }\n"
        "                selectedObject = null;\n"
        "                selectedObjectToEditCaption = null;\n"
        "                selectedObjectGroup = null;\n"
        "                break;\n"
        "            }\n")
    _gate_once(ca, handler_anchor, handler + handler_anchor, "ChatActivity sender options handlers")


def patch_selection_announce() -> None:
    """Say it out loud whenever something is picked or un-picked in a selection:

      * a message of a chat (tap while messages are being selected): \"Selected\" / \"Unselected\"
      * a chat of the chat list (long press to start, tap to add / remove): the same words

    TalkBack only knows the state of the row it is on; it said nothing at the moment of the change.
    The menu's own \"Select\" item keeps its single \"Selected\" (it calls the 3-argument method).
    """
    ca = JAVA / "org/telegram/ui/ChatActivity.java"
    _gate_once(
        ca,
        "    private void addToSelectedMessages(MessageObject messageObject, boolean outside) {\n"
        "        addToSelectedMessages(messageObject, outside, true);\n"
        "    }\n",
        "    private void addToSelectedMessages(MessageObject messageObject, boolean outside) {\n"
        "        final boolean a11yWasSelected = a11yIsMessageSelected(messageObject); // a11y-fork: say Selected / Unselected\n"
        "        addToSelectedMessages(messageObject, outside, true);\n"
        "        a11yAnnounceMessageSelection(messageObject, a11yWasSelected);\n"
        "    }\n\n"
        "    private boolean a11yIsMessageSelected(MessageObject m) {\n"
        "        try {\n"
        "            return m != null && selectedMessagesIds[m.getDialogId() == dialog_id ? 0 : 1].indexOfKey(m.getId()) >= 0;\n"
        "        } catch (Throwable e) {\n"
        "            return false;\n"
        "        }\n"
        "    }\n\n"
        "    private void a11yAnnounceMessageSelection(MessageObject m, boolean wasSelected) {\n"
        "        try {\n"
        "            if (m == null || getParentActivity() == null) {\n"
        "                return;\n"
        "            }\n"
        "            final boolean now = a11yIsMessageSelected(m);\n"
        "            if (now == wasSelected) {\n"
        "                return;\n"
        "            }\n"
        "            getParentActivity().getWindow().getDecorView().announceForAccessibility(LocaleController.getString(now ? R.string.A11ySelected : R.string.A11yUnselected));\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n"
        "    }\n",
        "ChatActivity message selection announce")
    # the menu's own Select item: use the 3-argument method so it is announced once, by its own code
    _gate_once(
        ca,
        "                        addToSelectedMessages(toSelect, false);\n"
        "                        updateActionModeTitle();\n",
        "                        addToSelectedMessages(toSelect, false, true);\n"
        "                        updateActionModeTitle();\n",
        "ChatActivity Select item announces once")
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "        if (selectedDialogs.contains(did)) {\n"
        "            selectedDialogs.remove(did);\n"
        "            if (cell instanceof DialogCell) {\n"
        "                ((DialogCell) cell).setChecked(false, true);\n"
        "            } else if (cell instanceof ProfileSearchCell) {\n"
        "                ((ProfileSearchCell) cell).setChecked(false, true);\n"
        "            }\n"
        "            return false;\n"
        "        } else {\n"
        "            selectedDialogs.add(did);\n"
        "            if (cell instanceof DialogCell) {\n"
        "                ((DialogCell) cell).setChecked(true, true);\n"
        "            } else if (cell instanceof ProfileSearchCell) {\n"
        "                ((ProfileSearchCell) cell).setChecked(true, true);\n"
        "            }\n"
        "            return true;\n"
        "        }\n",
        "        if (selectedDialogs.contains(did)) {\n"
        "            selectedDialogs.remove(did);\n"
        "            if (cell instanceof DialogCell) {\n"
        "                ((DialogCell) cell).setChecked(false, true);\n"
        "            } else if (cell instanceof ProfileSearchCell) {\n"
        "                ((ProfileSearchCell) cell).setChecked(false, true);\n"
        "            }\n"
        "            a11yAnnounceDialogSelection(cell, false); // a11y-fork: say Unselected\n"
        "            return false;\n"
        "        } else {\n"
        "            selectedDialogs.add(did);\n"
        "            if (cell instanceof DialogCell) {\n"
        "                ((DialogCell) cell).setChecked(true, true);\n"
        "            } else if (cell instanceof ProfileSearchCell) {\n"
        "                ((ProfileSearchCell) cell).setChecked(true, true);\n"
        "            }\n"
        "            a11yAnnounceDialogSelection(cell, true); // a11y-fork: say Selected\n"
        "            return true;\n"
        "        }\n"
        "    }\n\n"
        "    private void a11yAnnounceDialogSelection(View cell, boolean selected) {\n"
        "        try {\n"
        "            if (cell != null) {\n"
        "                cell.announceForAccessibility(LocaleController.getString(selected ? R.string.A11ySelected : R.string.A11yUnselected));\n"
        "            }\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n",
        "DialogsActivity chat selection announce")


def patch_dialogs_select_all() -> None:
    """Chat list: "Select all".

    As soon as a chat is selected (the selection bar with the count appears) its More options menu
    has "Select All": every chat of the list that is on the screen (the current tab / folder /
    archive) is selected, the count is updated and the number is spoken. Archive rows and the
    topics of forums in a picker are left out, like a long press leaves them out.
    """
    da = JAVA / "org/telegram/ui/DialogsActivity.java"
    _gate_once(
        da,
        "    private final static int community_ungroup = 111;\n",
        "    private final static int community_ungroup = 111;\n"
        "    private final static int a11y_select_all = 190; // a11y-fork: Select all chats\n",
        "DialogsActivity select-all id")
    _gate_once(
        da,
        "        archiveItem = otherItem.addSubItem(archive, R.drawable.msg_archive, LocaleController.getString(R.string.Archive));\n",
        "        otherItem.addSubItem(a11y_select_all, R.drawable.msg_select, LocaleController.getString(R.string.SelectAll)); // a11y-fork: Select all chats\n"
        "        archiveItem = otherItem.addSubItem(archive, R.drawable.msg_archive, LocaleController.getString(R.string.Archive));\n",
        "DialogsActivity select-all menu item")
    _gate_once(
        da,
        "            public void onItemClick(int id) {\n"
        "                if ((id == SearchViewPager.forwardItemId",
        "            public void onItemClick(int id) {\n"
        "                if (id == a11y_select_all) { // a11y-fork: Select all chats\n"
        "                    a11ySelectAllDialogs();\n"
        "                    return;\n"
        "                }\n"
        "                if ((id == SearchViewPager.forwardItemId",
        "DialogsActivity select-all click")
    _gate_once(
        da,
        "    public boolean addOrRemoveSelectedDialog(long did, View cell) {\n",
        "    // a11y-fork: select every chat of the list on the screen\n"
        "    private void a11ySelectAllDialogs() {\n"
        "        try {\n"
        "            if (viewPages == null || viewPages.length == 0 || viewPages[0] == null || selectedDialogs.isEmpty()) {\n"
        "                return;\n"
        "            }\n"
        "            final ViewPage page = viewPages[0];\n"
        "            final ArrayList<TLRPC.Dialog> list = getDialogsArray(currentAccount, page.dialogsType, folderId, dialogsListFrozen);\n"
        "            if (list == null) {\n"
        "                return;\n"
        "            }\n"
        "            for (int i = 0; i < list.size(); i++) {\n"
        "                final TLRPC.Dialog d = list.get(i);\n"
        "                if (d == null || d instanceof TLRPC.TL_dialogFolder || d.id == 0) {\n"
        "                    continue;\n"
        "                }\n"
        "                if (onlySelect && getMessagesController().isForum(d.id)) {\n"
        "                    continue;\n"
        "                }\n"
        "                if (!selectedDialogs.contains(d.id)) {\n"
        "                    selectedDialogs.add(d.id);\n"
        "                }\n"
        "            }\n"
        "            for (int i = 0; i < page.listView.getChildCount(); i++) {\n"
        "                final View child = page.listView.getChildAt(i);\n"
        "                if (child instanceof DialogCell) {\n"
        "                    ((DialogCell) child).setChecked(selectedDialogs.contains(((DialogCell) child).getDialogId()), true);\n"
        "                }\n"
        "            }\n"
        "            updateCounters(false);\n"
        "            selectedDialogsCountTextView.setNumber(selectedDialogs.size(), true);\n"
        "            if (fragmentView != null) {\n"
        "                fragmentView.announceForAccessibility(LocaleController.formatString(R.string.A11ySelectAllDone, selectedDialogs.size()));\n"
        "            }\n"
        "        } catch (Throwable e) {\n"
        "            FileLog.e(e);\n"
        "        }\n"
        "    }\n\n"
        "    public boolean addOrRemoveSelectedDialog(long did, View cell) {\n",
        "DialogsActivity select-all handler")


def main() -> int:
    if not Path("telegram").is_dir():
        print("ERROR: telegram/ not found (clone DrKLO/Telegram as ./telegram)", file=sys.stderr)
        return 1
    print("Using scripts dir:", SCRIPTS.resolve())
    apply_mehran_patch()
    MEHRAN = Path("telegram/.a11y-mehran-applied").exists()
    patch_app_name()
    install_a11y_config()
    patch_radial_progress()
    patch_dialogcell_name_then_type()
    patch_hide_share_and_comment()
    patch_forward_menu_extras()
    # Shared end-anchor order: Bot Buttons -> Reactions -> Select (Select last).
    patch_longpress_message_menu()
    patch_photo_longpress_message_options()
    patch_reactions_as_menu()
    patch_voice_bitrate()
    patch_settings_menu()
    patch_auto_download_policy()
    patch_small_file_localization()
    patch_small_file_download_mode()
    patch_exact_progress_steps()
    patch_recording_beep()
    patch_a11y_settings_dialog_stays_open()
    if MEHRAN:
        patch_dialogcell_preview_muted_status()
        patch_dialogcell_time_last()
    else:
        patch_dialogcell_preview_muted_status_legacy()
        patch_dialogcell_time_last_legacy()
    patch_chat_message_cell_float_coordinates()
    patch_hide_sponsor_channel()
    patch_ghost_mode()
    patch_bot_buttons_menu()
    patch_leave_comment_menu()
    patch_links_as_menu()
    patch_reorder_a11y_menu_items()
    patch_go_to_first_message()
    patch_file_description_spacing()
    patch_locale_controller_solar_date_chat()
    patch_solar_last_seen()
    if MEHRAN:
        patch_fork_selection_vs_options()
    patch_chat_message_cell_accessibility_long_click()
    patch_reply_forward_long_click()
    patch_every_node_long_click()
    if MEHRAN:
        patch_fork_quiet_download_state()
    if MEHRAN:
        patch_album_and_user_status_switches()
    patch_admin_tag_switch()
    patch_share_send_button_label()
    patch_chat_open_sound()
    patch_message_tap_sound()
    patch_proxy_toolbar_button()
    patch_old_style_menu()
    patch_old_menu_hides_tabs()
    patch_category_filter()
    patch_legacy_navigation_drawer()
    patch_old_menu_hides_options()
    patch_old_menu_extras()
    patch_dialog_row_tap_sound()
    patch_voice_share()
    patch_player_seek_buttons()
    patch_sender_options_menu()
    patch_selection_announce()
    patch_dialogs_select_all()
    patch_unlabeled_buttons()
    patch_audit_unlabeled_buttons()
    patch_contacts_list_accessibility()
    patch_topics_hide_chat_list_from_screen_reader()
    patch_more_unlabeled_buttons()
    patch_reply_longpress_opens_options()
    patch_longclickable_flag()
    if not MEHRAN:
        patch_chat_message_cell_granularity_navigation_legacy()
    patch_stuck_together_bubbles_long_press()
    if MEHRAN:
        patch_mehran_strings_persian()
    # MUST stay last: it rewrites English text injected by the patches above
    # (Selected / Bot Buttons / Forwarded to Saved / Accessible settings ...).
    patch_a11y_localization()
    print("A11y REAL patches done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
