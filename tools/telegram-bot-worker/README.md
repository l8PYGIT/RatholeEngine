# ربات سرورلس اعلان آپدیت‌های گیتهاب در تلگرام

این پوشه و اسکریپت [`../telegram_notify.py`](../telegram_notify.py) دو روش **کاملاً رایگان و سرورلس** برای ارسال خودکار اعلان ریلیزها و آپدیت‌های گیتهاب به کانال یا گروه تلگرام (با تصویر بنر، فرمت HTML تمیز و دکمه‌های شیشه‌ای Inline) ارائه می‌دهند:

---

## روش ۱ — GitHub Actions Reusable Workflow (پیشنهادی، بدون نیاز به سرویس خارجی)

ورک‌فلو [`.github/workflows/telegram-notify.yml`](../../.github/workflows/telegram-notify.yml) داخل خود **RatholeEngine** فعال است و بعد از ساخت فایل‌های ریلیز به‌طور خودکار صدا زده می‌شود.

### فعال‌سازی روی مخزن فعلی (`l8PYGIT/RatholeEngine`)
1. در تلگرام با [@BotFather](https://t.me/BotFather) ربات بسازید و آن را به‌عنوان **Admin** (با دسترسی Post Messages) به کانال اضافه کنید.
2. در گیتهاب وارد `Settings → Secrets and variables → Actions` شوید و دو Secret زیر را اضافه کنید:
   - `TELEGRAM_BOT_TOKEN`: توکن ربات
   - `TELEGRAM_CHAT_ID`: آیدی عددی کانال (مثلاً `-1001234567890`) یا یوزرنیم کانال عمومی (`@l8PY4NET`)

### استفاده در سایر ریپوهای گیتهاب شما (فقط ۶ خط YAML)
در هر مخزن دیگری کافی است همین دو Secret را ست کنید و فایل `.github/workflows/announce.yml` بسازید:

```yaml
name: Telegram Announce
on:
  release:
    types: [published]
jobs:
  telegram:
    uses: l8PYGIT/RatholeEngine/.github/workflows/telegram-notify.yml@main
    with:
      tag: ${{ github.event.release.tag_name }}
      channel: "@l8PY4NET"
    secrets: inherit
```

---

## روش ۲ — Cloudflare Worker Webhook (یک آدرس واحد برای همهٔ ریپوها)

اگر می‌خواهید بدون اضافه کردن فایل `.github/workflows` به تک‌تک ریپوها، یک Webhook مرکزی روی **حساب کاربری / کل مخازن جدید** داشته باشید:

```bash
cd tools/telegram-bot-worker
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID      # مثلا @l8PY4NET یا -100...
npx wrangler secret put GITHUB_WEBHOOK_SECRET # یک رمز تصادفی قوی
npx wrangler deploy
```

سپس در تنظیمات مخزن (یا Organization) گیتهاب به بخش **Settings → Webhooks → Add webhook** بروید:
- **Payload URL:** آدرس `.workers.dev` خروجی دستور بالا
- **Content type:** `application/json`
- **Secret:** همان `GITHUB_WEBHOOK_SECRET`
- **Events:** گزینهٔ **Let me select individual events** را بزنید و تیک **Releases** (و در صورت نیاز `Repositories` / `Pushes`) را بگذارید.

> برای اعلان Pushهای شاخهٔ پیش‌فرض یا مخازن تازه، در [`wrangler.toml`](wrangler.toml) مقدار `NOTIFY_PUSH = "true"` یا `NOTIFY_NEW_REPO = "true"` را روشن کنید و دوباره deploy بزنید.

## فیلتر پیش‌فرض اعلان ریلیزها (سکوت برای Patch و Pre-release)
- به‌طور پیش‌فرض، ریلیزهای پچ (`vX.Y.Z` با `Z != 0` مثل `v2.1.1`)، پیش‌انتشارها (`-beta` / `-rc` / `-alpha`) و ریلیزهایی که در متن خود مارکر `<!-- no-telegram -->` یا `[no-telegram]` / `[skip-telegram]` داشته باشند، به کانال تلگرام ارسال **نمی‌شوند**.
- نسخه‌های اصلی/فرعی پایدار (`vX.Y.0` مثل `v2.1.0` یا `v2.2.0`) به‌صورت خودکار اعلان می‌شوند.
- این رفتار با ورودی `skip_patches` / `skip_prereleases` در ورک‌فلو یا متغیرهای `SKIP_PATCH_RELEASES` / `SKIP_PRERELEASES` در Worker قابل تنظیم است؛ همچنین اجرای دستی `workflow_dispatch` روی [`telegram-notify.yml`](../../.github/workflows/telegram-notify.yml) همچنان می‌تواند هر تگی را اعلان کند.
