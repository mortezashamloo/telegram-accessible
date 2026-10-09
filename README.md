# telegram-a11y / تلگرام دسترس‌پذیر

**English** | **[فارسی](#فارسی)**

TalkBack-friendly patches for official [Telegram Android](https://github.com/DrKLO/Telegram), plus a GitHub Actions workflow to build an APK **without a powerful PC**.

> This is an **accessibility fork kit** (patches + CI), not the official Telegram app.  
> Package id: `com.shamloo.telegram.accessible` (installs **next to** official Telegram).

---

## Features (TalkBack)

Everything below is applied by `scripts/apply-a11y.py` on top of the latest official source. Options marked **(setting)** live in **Settings → Accessible settings** and are **off by default** unless a default is given.

### Chat list
- Chat name first, then its type (e.g. "Grok, channel"); "Muted" is not read; longer message preview.
- Sent / received time is read last, in Telegram's own wording.
- **(setting)** Contact status (online / last seen) in the preview — default **on**.
- **(setting)** Hide the sponsored channel.
- **(setting)** Category filter button: All / Private chats / Groups / Channels / Bots.
- "Selected" / "Unselected" is spoken when a chat is picked; **Select all** in the selection bar's More options.

### Reading messages
- Upload / download **percent** is announced only while TalkBack focus is on that message; the step (1 / 5 / 10 / 20 %) is a **(setting)**.
- Files are read as "File: name" with the real file name, not a long number.
- Share and the on-bubble Leave comment button are hidden between messages.
- Reading by character and by word works inside a message.
- **(setting)** Media album grouping ("photo 2 of 5"), admin / owner tags, "Downloaded / not downloaded" status, user status (typing, recording, online).
- **(setting)** Solar (Persian) calendar for date headers and last seen.
- **(setting)** Touch click sound when a chat opens or a message is tapped.

### Message options (long-press)
- Long-press opens the single-message menu, also on replies, files and photos.
- **Leave comment** (with the comment count) is the first item; **Select** is the last.
- **Bot buttons** — one item that opens the real bot actions.
- **Reactions** — one item instead of a reaction strip in the way.
- **Forward without quote** and **Forward to Saved Messages** next to Forward; **(setting)** Saved Messages without quote.
- **(setting)** **Forward here** — sends the message again into the same chat.
- **(setting)** **Links** — lists the links and @mentions of a message as written; t.me links open inside Telegram.
- **(setting)** Sender options (profile, send message, mention, search).
- **(setting)** Share and Save to music for voice messages.

### Voice and audio
- Voice message quality: Low / Medium (default) / High.
- Vibration when recording starts; **(setting)** start beep.
- **(setting)** Rewind and forward buttons in the audio player bar.

### Menus and toolbar
- **(setting)** Main menu style: current Telegram (bottom tabs) / old-style popup menu / classic side drawer (My Profile, New Group, New Channel, Contacts, Calls, Saved Messages, Settings, Invite Friends, Telegram Features). The classic drawer needs the app reopened.
- **(setting)** Proxy button in the chat list toolbar.
- The Accessible settings dialog stays open while you change options.

### Network and privacy
- **(setting)** Ghost mode: read receipts are not sent to the server.
- **(setting)** Auto-download of small files: automatic / voice messages only (default) / none.

### Other
- Labels for unlabeled buttons (settings, contacts, video player, add member, and more).
- Persian and English texts through `LocaleController`.
- Features ported from Mehran Latifi's fork (see Credits).
- APK size: **arm64-v8a only**; own package id and private signing key.

---

## For screen reader users (quick)

1. Open the repo on GitHub (or your fork).
2. **Actions** → **Build APK** → **Run workflow**.
3. Wait (often ~45–90 minutes the first times).
4. Download artifact **`telegram-accessible-arm64`** (and once: **`a11y-release-keystore`**).
5. Install the APK (Unknown sources / install from files as on your device).
6. Optional: save the keystore as GitHub **Secrets** so the **next** build can update the same install (same signature).

If Play Protect warns on older public debug builds, this kit uses a **unique package** and a **private keystore** so warnings are usually milder. Sideloaded apps may still show a soft warning; that is normal outside Play Store.

---

## One-time GitHub setup

### Required secrets

| Secret | Where from |
|--------|------------|
| `TELEGRAM_API_ID` | [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | same |

### Recommended secrets (stable updates / Play Protect kit)

| Secret | Typical value |
|--------|----------------|
| `A11Y_KEYSTORE_BASE64` | Base64 of `a11y-release.keystore` (from the workflow artifact) |
| `A11Y_STORE_PASSWORD` | `telegram-a11y-local` (if you used defaults) |
| `A11Y_KEY_PASSWORD` | same as store password |
| `A11Y_KEY_ALIAS` | `a11ykey` |

**Windows (PowerShell) — copy keystore to clipboard as Base64:**

```powershell
Set-Clipboard -Value ([Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\Users\YOU\Downloads\a11y-release.keystore")))
```

Then: repo **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Order of secrets does **not** matter. A trailing blank line in Base64 is usually OK (CI trims it).

---

## Build your own fork (another blind developer / friend)

1. Fork this repo **or** create an empty repo and copy `scripts/` and `.github/workflows/`.
2. Add secrets above on **your** fork.
3. Run **Build APK**.
4. Keep **your** keystore private; do not commit it to git.
5. Respect [Telegram API Terms](https://core.telegram.org/api/terms) and **GPL-2.0** when you share APKs.

You do **not** need the official Telegram Play signing key. This kit generates **`a11y-release.keystore`**. That key is only for *your* builds — Google does **not** “whitelist” it as safe; it only keeps package id + signature stable.

---

## Releases on GitHub

After a good build:

1. Download the APK artifact from Actions.
2. Repo → **Releases** → **Create a new release**.
3. Tag e.g. `v1.0.0-a11y`, title e.g. `Telegram Accessible (arm64)`.
4. Upload the APK (+ short notes: TalkBack features, arm64-only, package id).
5. Paste a short English + Persian changelog.

Maintainers: prefer attaching the CI APK rather than rebuilding on a laptop.

See also [RELEASE_NOTES_TEMPLATE.md](RELEASE_NOTES_TEMPLATE.md).

---

## Project layout

```
.github/workflows/build-apk.yml    # CI build
scripts/apply-a11y.py              # core TalkBack patches (applied on a fresh DrKLO/Telegram clone)
scripts/A11yConfig.java            # Accessible Settings (copied into the source by apply-a11y.py)
scripts/mehran-a11y.patch          # features ported from Mehran Latifi's fork
scripts/inject-api.py              # API ID / HASH from GitHub Secrets
scripts/prepare-release-signing.py # private keystore + google-services
scripts/slim-arm64.py              # arm64-only APK
```

The package id (`com.shamloo.telegram.accessible`) is set by the workflow step "Set package name".

---

## Credits

Many accessibility features (for example playback position and labels for unlabeled buttons) come from the fork of **Mehran Latifi**: <https://github.com/mehranlatifi83/Telegram> — thank you.

---

## License

Minimal patches for use with Telegram Android (**GPL-2.0**).  
Not affiliated with Telegram FZ-LLC. Use at your own risk.

---

# فارسی

پچ‌های دوستدار **TalkBack** برای [تلگرام اندروید رسمی](https://github.com/DrKLO/Telegram) + بیلد با **GitHub Actions** بدون نیاز به سیستم قوی.

> این یک **کیت دسترس‌پذیری** است (پچ + CI)، نه اپ رسمی تلگرام.  
> شناسه پکیج: `com.shamloo.telegram.accessible` (کنار تلگرام رسمی نصب می‌شود).

## قابلیت‌ها (TalkBack)

همهٔ موارد زیر را `scripts/apply-a11y.py` روی آخرین سورس رسمی اعمال می‌کند. گزینه‌های علامت‌خورده با **(تنظیم)** در **Settings ← Accessible settings** هستند و مگر پیش‌فرض ذکر شده باشد، **خاموش**‌اند.

### لیست چت
- اول نام چت، بعد نوعش (مثلاً «گراک، کانال»)؛ کلمهٔ «Muted» خوانده نمی‌شود؛ پیش‌نمایش پیام بلندتر.
- زمان ارسال / دریافت آخر از همه و با همان عبارت خود تلگرام خوانده می‌شود.
- **(تنظیم)** وضعیت مخاطب (آنلاین / آخرین بازدید) در پیش‌نمایش — پیش‌فرض **روشن**.
- **(تنظیم)** مخفی کردن کانال حامی.
- **(تنظیم)** دکمهٔ فیلتر دسته‌بندی: همه / چت خصوصی / گروه‌ها / کانال‌ها / ربات‌ها.
- هنگام انتخاب چت «Selected» / «Unselected» گفته می‌شود؛ **Select all** در More options نوار انتخاب.

### خواندن پیام‌ها
- **درصد** آپلود / دانلود فقط وقتی فوکوس TalkBack روی همان پیام است اعلام می‌شود؛ گام آن (۱ / ۵ / ۱۰ / ۲۰ درصد) **(تنظیم)** است.
- فایل‌ها به شکل «File: نام» با نام واقعی خوانده می‌شوند، نه عدد طولانی.
- Share و دکمهٔ Leave comment روی حباب بین پیام‌ها مخفی است.
- خواندن حرف‌به‌حرف و کلمه‌به‌کلمه داخل پیام کار می‌کند.
- **(تنظیم)** گروه‌بندی آلبوم («عکس ۲ از ۵»)، تگ ادمین / مالک، وضعیت «دانلود‌شده / دانلود‌نشده»، وضعیت کاربر (در حال تایپ، ضبط، آنلاین).
- **(تنظیم)** تقویم خورشیدی برای سرتیتر تاریخ‌ها و آخرین بازدید.
- **(تنظیم)** صدای لمس هنگام باز شدن چت یا ضربه روی پیام.

### گزینه‌های پیام (long-press)
- long-press منوی تک‌پیام را باز می‌کند، روی ریپلای، فایل و عکس هم.
- **Leave comment** (با تعداد کامنت) اولین آیتم است و **Select** آخرین.
- **Bot buttons** — یک آیتم که دکمه‌های واقعی ربات را باز می‌کند.
- **Reactions** — یک آیتم، به‌جای نوار واکنشِ مزاحم.
- **Forward without quote** و **Forward to Saved Messages** کنار Forward؛ **(تنظیم)** ذخیره‌شده‌ها بدون نقل‌قول.
- **(تنظیم)** **Forward here** — پیام را دوباره در همان چت می‌فرستد.
- **(تنظیم)** **Links** — لینک‌ها و @منشن‌های پیام را همان‌طور که نوشته شده فهرست می‌کند؛ لینک‌های t.me داخل تلگرام باز می‌شوند.
- **(تنظیم)** گزینه‌های فرستنده (پروفایل، ارسال پیام، منشن، جستجو).
- **(تنظیم)** Share و Save to music برای پیام‌های صوتی.

### ویس و صدا
- کیفیت پیام صوتی: Low / Medium (پیش‌فرض) / High.
- لرزش هنگام شروع ضبط؛ **(تنظیم)** بوق شروع ضبط.
- **(تنظیم)** دکمه‌های عقب و جلو در نوار پخش‌کنندهٔ صدا.

### منوها و نوار بالا
- **(تنظیم)** سبک منوی اصلی: تلگرام فعلی (نوار پایین) / منوی قدیمی پاپ‌آپ / منوی کشویی کلاسیک (My Profile، New Group، New Channel، Contacts، Calls، Saved Messages، Settings، Invite Friends، Telegram Features). منوی کشویی نیاز به باز کردن دوبارهٔ برنامه دارد.
- **(تنظیم)** دکمهٔ پروکسی در نوار بالای لیست چت.
- پنجرهٔ Accessible settings هنگام تغییر گزینه‌ها بسته نمی‌شود.

### شبکه و حریم خصوصی
- **(تنظیم)** حالت روح: رسید خواندن به سرور فرستاده نمی‌شود.
- **(تنظیم)** دانلود خودکار فایل‌های کم‌حجم: خودکار / فقط پیام‌های صوتی (پیش‌فرض) / هیچ.

### سایر
- برچسب برای دکمه‌های بدون برچسب (تنظیمات، مخاطبین، پخش ویدیو، افزودن عضو و ...).
- متن‌های فارسی و انگلیسی با `LocaleController`.
- قابلیت‌های برگرفته از فورک مهران لطیفی (بخش قدردانی).
- حجم کمتر: فقط **arm64-v8a**؛ شناسهٔ پکیج و کلید امضای اختصاصی.

## راهنمای سریع کاربران صفحه‌خوان

1. ریپو (یا فورک خودت) را در گیت‌هاب باز کن.
2. **Actions** → **Build APK** → **Run workflow**.
3. صبر کن (اغلب حدود ۴۵ تا ۹۰ دقیقه).
4. Artifactهای **`telegram-accessible-arm64`** و یک‌بار **`a11y-release-keystore`** را دانلود کن.
5. APK را نصب کن.
6. برای آپدیت بعدی روی همان نصب: keystore را در **Secrets** بگذار (جدول بالا).

## راه‌اندازی Secrets

الزامی: `TELEGRAM_API_ID` و `TELEGRAM_API_HASH` از [my.telegram.org](https://my.telegram.org).

پیشنهادی برای امضای ثابت:

- `A11Y_KEYSTORE_BASE64` — خروجی Base64 فایل `a11y-release.keystore`
- `A11Y_STORE_PASSWORD` — پیش‌فرض: `telegram-a11y-local`
- `A11Y_KEY_PASSWORD` — معمولاً همان
- `A11Y_KEY_ALIAS` — پیش‌فرض: `a11ykey`

**ویندوز — کپی Base64 به کلیپ‌بورد:**

```powershell
Set-Clipboard -Value ([Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\Users\YOU\Downloads\a11y-release.keystore")))
```

ترتیب secretها مهم نیست.

## فورک برای خودت

1. این ریپو را Fork کن (یا فایل‌های `scripts/` و workflow را کپی کن).
2. Secrets را روی **فورک خودت** بگذار.
3. بیلد بگیر.
4. keystore را عمومی نکن و داخل git commit نکن.
5. شرایط API تلگرام و GPL را رعایت کن.

کلید امضای فروشگاه تلگرام لازم نیست؛ کیت **`a11y-release.keystore`** می‌سازد. گوگل این کلید را «تأیید امن» نمی‌کند؛ فقط پکیج و امضای تو را پایدار نگه می‌دارد.

## انتشار (Releases)

1. APK را از Actions بگیر.
2. **Releases** → **Create a new release**.
3. تگ مثلاً `v1.0.0-a11y`.
4. APK را ضمیمه کن و خلاصهٔ فارسی/انگلیسی بنویس (TalkBack، arm64، نام پکیج).

نیز ببینید: [RELEASE_NOTES_TEMPLATE.md](RELEASE_NOTES_TEMPLATE.md).

## مجوز

پچ‌های حداقلی برای تلگرام اندروید (**GPL-2.0**).  
وابسته به Telegram FZ-LLC نیست. با مسئولیت خودتان استفاده کنید.

## قدردانی

بخش بزرگی از قابلیت‌های دسترس‌پذیری (مثل موقعیت پخش و برچسب دکمه‌های بدون برچسب) از فورک **مهران لطیفی** گرفته شده: <https://github.com/mehranlatifi83/Telegram> — سپاس.
