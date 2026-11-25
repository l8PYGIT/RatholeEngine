# RatholeEngine Wiki

خوش آمدید به مستندات جامع و ویکی پروژه **RatholeEngine**.

این سیستم یک راهکار **معکوس‌تونل (Reverse Tunnel)** پیشرفته و چندموقعیتی بر پایه‌ی **rathole + Nginx** برای عبور از فیلترینگ شدید است. در نسخه‌های اخیر، کنار lane رتهول چند **هسته‌ی مستقل** هم اضافه شده است: **Backhaul (SMUX)**، **FRP**، تونل لایه‌۳ **GRE**، حالت ترکیبی **FRP + GRE** و **Paqet (Direct PCK)**؛ به‌علاوه‌ی **REST Agent** و **Reverse WebSocket Agent (`reverse_ws`)** که اجازه می‌دهد هاب سرورهای پشت NAT یا دارای IP فیلترشده را هم بدون SSH و بدون هیچ پورت ورودی باز مدیریت کند.

> نسخه‌ی فعلی: **v2.4.0** — اضافه شدن **Reverse WebSocket Agent (`reverse_ws`)** برای اتصال خروجی از نودهای فیلترشده به `/hub/ws/agent` (پشت پورت ۴۴۳ Nginx) به‌همراه **محافظ دوفازه‌ای Watchdog (`--confirm-ttl` + `bench confirm`)** و سخت‌سازی ایمنی کرنل/سرویس در موتور **تیونر شبکه `rathole-tuner`** (با پروفایل‌های **`rthprof1:` / JSON** و صفحه **`#/tuner`**)، در کنار حامل **Paqet**، **Managed Xray** (`VLESS+REALITY+Vision` / `XHTTP` + اسکنر سایت کاور TLS 1.3)، مانیتور و ربات تلگرام چندمسیره، توکن‌های RBAC، TOTP 2FA، `/metrics` پرومتئوس و آپدیت با امضای Ed25519.

![داشبورد RatholeHub — نسخهٔ نمایشی](https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/docs/assets/screenshots/dashboard.png)

> 🌐 **نسخهٔ وب مستندات:** همین محتوا به‌صورت یک **وب‌سایت استاتیک** هم قابل ساخت است. راهنمای ساخت/انتشار و مقایسهٔ پلتفرم‌های ویکی وب (MkDocs Material، VitePress — که مرزبان استفاده می‌کند —، Docusaurus و Docsify) در [`docs/website.md`](https://github.com/l8PYGIT/RatholeEngine/blob/main/docs/website.md) آمده است.

---

## 📚 فهرست صفحات ویکی (Wiki Index)

1. 🚀 **[راهنمای شروع سریع (Getting Started)](Getting-Started)**
   - نصب خودکار یک‌خطی و گزینه‌های نصب (Panel / Node / Hub)
   - پرچم‌های جدید: pin کردن نسخه (`--release`) و مخزن خصوصی (`--token`)
   - جداکننده‌ی `--` برای آرگومان‌های نصب نود
   - راه‌اندازی سریع REST Agent و نمای کلی حامل‌ها

2. ⚡ **[راهنمای Adaptive Filtering (سوئیچ خودکار)](Adaptive-Filtering-Guide)**
   - منطق سوئیچینگ هوشمند بین حامل‌ها و زنجیره fallback
   - پروب لایه‌ای برای هر حامل (ws / plain / kcp / backhaul / frp)
   - تنظیم فواصل، آستانه (Threshold) و Cooldown
   - چرا انتخاب دستی حامل بر Adaptive اولویت دارد

3. 📖 **[مرجع کامل دستورات CLI (CLI Reference)](CLI-Reference)**
   - دستورات سرور ایران (`ratholectl`) و نود خارج (`ratholenode`)
   - مدیریت REST و Reverse WS Agent (`agent on|reverse|off|status|token`)، **Managed Xray** (`xray`) و **`bench` (`rathole-tuner`)**
   - ۹ حامل: WS، KCP، Plain، Noise، **Backhaul (SMUX)**، **FRP** (`7000/TCP` + `7000/UDP`)، **GRE**، **FRP + GRE** و **Paqet (Direct PCK)**
   - مسیر مخفی کنترلی (`control-path`)، upstream چندسروره، `migrate` و `set-main`
   - آپدیت، بک‌آپ و رول‌بک

4. 🖥️ **[مدیریت مرکزی با Hub (Hub Management)](Hub-Management)**
   - نصب و کانفیگ پنل وب Hub (`hub.py`) با رابط Apple Glass، `⌘K / Ctrl+K` و **`#/tuner`**
   - سلکتور یک‌کلیکی حامل، منوی `⋯` کنترل سرویس‌ها، Paqet/Xray و مانیتور تلگرام
   - اتصال **Reverse WebSocket (`reverse_ws`)**، REST Agent مستقیم و SSH
   - REST API، مدل امنیتی، 2FA/RBAC و آپدیت گروهی با امضای Ed25519

5. 🛠️ **[عیب‌یابی، بک‌آپ و رول‌بک (Troubleshooting)](Troubleshooting)**
   - عیب‌یابی اتصالات، تاریخچه `state.json` و `history`/`undo`
   - خطاهای REST و Reverse WS Agent (`reverse_ws`، خطای 401/403، `--insecure-ssl`، پروکسی) و رول‌بک Watchdog تیونر
   - ناسازگاری حامل‌ها (پروتکل `?`، توکن/profile بک‌هال، MTU و probe در GRE، پورت UDP ۷۰۰۰ و transport در FRP)
   - آپدیت از مخزن خصوصی و رول‌بک

6. 📋 **[راهنماهای عملی (Workflow Guides)](Workflow-Guides)**
   - راه‌اندازی REST Agent مستقیم یا **Reverse WebSocket (`reverse_ws`)** برای نود فیلترشده/پشت NAT
   - تغییر حامل یک سرویس با کنترل‌های سرویس (همگام‌سازی دو سمت)
   - اجرای بنچمارک `rathole-tuner`، تحلیل AI با `rthprof1:`، تست A/B/N و اعمال دوفازه‌ای (`--confirm-ttl 45`)
   - مهاجرت Backhaul ↔ Noise، راه‌اندازی direct-IP، دامنه دوم، multi-upstream و آپدیت مخزن خصوصی

---

## 🆕 تازه در نسخه‌های ۲.۱ تا ۲.۴.۰

| موضوع | خلاصه |
|-------|-------|
| **Reverse WS Agent و سخت‌سازی کرنل (`v2.4.0`)** | ایجنت WebSocket معکوس خالص stdlib (`wsutil.py` + `ratholeagent.py` v2.0.0) روی `/hub/ws/agent` بدون نیاز به پورت ورودی باز (با تبدیل یک‌کلیکی سرورهای آفلاین در هاب)، به‌همراه محافظ دوفازه‌ای Watchdog ددمن (`--confirm-ttl 45` + `bench confirm`)، حفظ `src`/`onlink` در route، بافر پیش‌فرض ایمن `262144`، پرش از offload `[fixed]` و رول‌بک صحیح `tc qdisc del root`. |
| **تستر و تیونر بی‌رحمانه (`v2.3.0`)** | موتور ۶ مرحله‌ای `rathole-tuner` (`ratholectl|ratholenode bench` و صفحه `#/tuner` هاب): بررسی باینری PMTU/MSS، آف‌لودها، BBR/CAKE/FQ، بافرها، Bufferbloat، مقایسه حامل‌ها، ممیزی غیرکرنلی، Watchdog بازگشت خودکار و خروجی قابل‌حمل **`rthprof1:` / JSON** با تست زنده A/B/N. |
| **حامل Paqet و Managed Xray (`v2.2.0`)** | حامل خام Direct PCK بدون هندشیک TLS، راه‌اندازی خودکار `VLESS+REALITY+Vision` و `XHTTP` روی نودها و اسکنر هم‌زمان سایت کاور TLS 1.3 + ALPN `h2`. |
| **مانیتور تلگرام، امنیت هاب و Ed25519 (`v2.2.0`)** | سرویس مستقل `ratholemonitor.service` با رله چندمسیره (`direct`/`proxy`/`node_tunnel`)، TOTP 2FA، توکن‌های RBAC، `/metrics` پرومتئوس، لاگ ممیزی SHA-256، تست دوطرفه لینک، کشف انحراف ناوگان و آپدیت با امضای Ed25519. |
| **ربات سرورلس تلگرام (`v2.1.0`)** | [`tools/telegram_notify.py`](https://github.com/l8PYGIT/RatholeEngine/blob/main/tools/telegram_notify.py) + ورک‌فلوی [`.github/workflows/telegram-notify.yml`](https://github.com/l8PYGIT/RatholeEngine/blob/main/.github/workflows/telegram-notify.yml) + Cloudflare Worker در `tools/telegram-bot-worker/` برای اعلان خودکار ریلیزها در کانال تلگرام با بنر و دکمه‌های Inline. |
| **رابط شیشه‌ای Apple Glass (`v2.1.0`–`v2.3.0`)** | تم روشن / تاریک / هماهنگ با سیستم، فونت آفلاین `vazirmatn.woff2` (بدون CDN)، ۴ کارت KPI، فیلتر زنده در داشبورد/جداول/audit و پالت فرمان **`⌘K / Ctrl+K`**. |
| **سلکتور حامل + منوی `⋯`** | تغییر یک‌کلیکی حامل در ردیف نود (همگام‌سازی خودکار دوطرفه با پیام وضعیت شفاف و بازگشت در صورت خطا)؛ ۵ اکشن سرویس زیر دکمه‌ی تک‌خطی `⋯`. |

---

## 📢 ارتباط و پشتیبانی

کانال تلگرام: **[t.me/l8PY4NET](https://t.me/l8PY4NET)** — اعلان نسخه‌های جدید، نکته‌های راه‌اندازی و سریع‌ترین جای پرسیدن سؤال.
گزارش باگ/درخواست ویژگی: **[GitHub Issues](https://github.com/l8PYGIT/RatholeEngine/issues)**

---

## 📜 لایسنس (License)

پروژه تحت لایسنس **[AGPL-3.0-or-later](https://github.com/l8PYGIT/RatholeEngine/blob/main/LICENSE)** به‌صورت متن‌باز منتشر شده است.

نسخه‌های تا v1.7.0 تحت MIT منتشر شده بودند و همچنان تحت MIT در دسترس‌اند؛ از آن پس پروژه AGPL-3.0 است.
نکته‌ی عملی (بند ۱۳ AGPL): اگر RatholeEngine را تغییر دهید و دیگران از طریق شبکه با نسخه‌ی تغییریافته‌ی شما
کار کنند (مثلاً پنل وب `ratholehub` را برایشان اجرا کنید)، باید سورس نسخه‌ی خود را به آن‌ها ارائه دهید.
جزئیات در [NOTICE](https://github.com/l8PYGIT/RatholeEngine/blob/main/NOTICE).
