# کیت پشتیبان Telegram Accessible

وقتی سورس رسمی [DrKLO/Telegram](https://github.com/DrKLO/Telegram) آپدیت شد، همین کیت دوباره روی آخرین سورس اعمال می‌شود.

## چه فایل‌هایی نگه داشته شود

```
scripts/
  apply-a11y.py              ← موتور اصلی پچ‌ها
  A11yConfig.java            ← تنظیمات Accessible Settings (باید کنار apply-a11y.py باشد)
  mehran-a11y.patch          ← قابلیت‌های فورک مهران
  inject-api.py              ← API ID / HASH
  prepare-release-signing.py ← امضا و google-services
  slim-arm64.py              ← فقط arm64
.github/workflows/build-apk.yml
README.md
RELEASE_NOTES_TEMPLATE.md
```

**اینها را در Drive نگذار:** `TELEGRAM_API_ID`، `TELEGRAM_API_HASH` و keystore / رمزهایش. فقط در GitHub Secrets بمانند.

## بیلد

1. GitHub → Actions → **Build APK** → **Run workflow**
2. artifact به نام `telegram-accessible-arm64` را دانلود کن.

نام پکیج: `com.shamloo.telegram.accessible`

## اگر WARN دیدی

اگر `apply-a11y.py` بگوید `WARN: ... not found` یعنی تلگرام آن تکه کد را عوض کرده؛ همان تابع باید با کد جدید هماهنگ شود.
