# telegram-accessible / تلگرام دسترس‌پذیر

**English** | **[فارسی](#فارسی)**

TalkBack-friendly patches for official [Telegram Android](https://github.com/DrKLO/Telegram), plus 

> This is an **accessibility fork kit** (patches + CI), not the official Telegram app.  
> Package id: `com.shamloo.telegram.accessible` (installs **next to** official Telegram).

---

## Features (TalkBack)

Everything below is applied by `scripts/apply-a11y.py` on top of the latest official source. Options marked **(setting)** live in **Settings → Accessible settings** and are **off by default** unless a default is given.

### Chat list
- Chat name first, then its type (e.g. "Morteza, channel"); "Muted" is not read; longer message preview.
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

update the same install (same signature).

If Play Protect warns on older public debug builds, this kit uses a **unique package** and a **private keystore** so warnings are usually milder. Sideloaded apps may still show a soft warning; that is normal outside Play Store.

---

---



## Credits

Many accessibility features (for example playback position and labels for unlabeled buttons) come from the fork of **Mehran Latifi**: <https://github.com/mehranlatifi83/Telegram> — thank you.

---

## License

Minimal patches for use with Telegram Android (**GPL-2.0**).  
Not affiliated with Telegram FZ-LLC. Use at your own risk.

---

# فارسی

پچ‌های دوستدار **TalkBack** برای [تلگرام اندروید رسمی](https://github.com/DrKLO/Telegram) +با 

> این یک **کیت دسترس‌پذیری** است (پچ + CI)، نه اپ رسمی تلگرام.  
> شناسه پکیج: `com.shamloo.telegram.accessible` (کنار تلگرام رسمی نصب می‌شود).

## قابلیت‌ها (TalkBack)

همهٔ موارد زیر را `scripts/apply-a11y.py` روی آخرین سورس رسمی اعمال می‌کند. گزینه‌های علامت‌خورده با **(تنظیم)** در **Settings ← Accessible settings** هستند و مگر پیش‌فرض ذکر شده باشد، **خاموش**‌اند.

### لیست چت
- اول نام چت، بعد نوعش (مثلاً «مرتضی، کانال»)؛ کلمهٔ «Muted» خوانده نمی‌شود؛ پیش‌نمایش پیام بلندتر.
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


## مجوز

پچ‌های حداقلی برای تلگرام اندروید (**GPL-2.0**).  
وابسته به Telegram FZ-LLC نیست. با مسئولیت خودتان استفاده کنید.

## قدردانی

بخش بزرگی از قابلیت‌های دسترس‌پذیری (مثل موقعیت پخش و برچسب دکمه‌های بدون برچسب) از فورک **مهران لطیفی** گرفته شده: <https://github.com/mehranlatifi83/Telegram> — سپاس.
