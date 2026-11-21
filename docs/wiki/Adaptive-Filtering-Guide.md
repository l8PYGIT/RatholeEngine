# راهنمای جامع Adaptive Filtering (سوئیچ خودکار)

ویژگی **Adaptive Filtering** (از v1.5.0) به نودهای خارج اجازه می‌دهد بدون دخالت اپراتور، در صورت فیلتر یا اختلال در حامل فعلی تونل، به حامل جایگزین سوئیچ کنند. این صفحه با کد `ratholenode` در **v2.0.2** تطبیق داده شده است.

---

## منطق پروب‌های لایه‌ای

هر دور، بر اساس `TUNNEL` فعلی نود یک probe اجرا و نتیجه در `adaptive-state.json` طبقه‌بندی می‌شود:

| حامل فعلی (`TUNNEL`) | probe | طبقه‌بندی‌های ممکن |
|----------------------|-------|---------------------|
| `ws` | handshake وب‌سوکت RFC 6455 روی TLS به `CONTROL_PATH` (پیش‌فرض `/`) | `healthy`، `tls_failed`، `ws_rejected` |
| `plain` | handshake وب‌سوکت بدون TLS به `PLAIN_REMOTE` روی مسیر `/` | `healthy`، `ws_timeout`، `ws_rejected` |
| `kcp` | بررسی TCP روی listener لوکال kcptun (`KCP_LOCAL`، پیش‌فرض `127.0.0.1:29900`) | `healthy`، `tcp_timeout`، `tcp_refused` |
| `backhaul` | handshake وب‌سوکت به `/channel` همراه هدر `Authorization: Bearer <BH_TOKEN>` (TLS/plain بسته به `BH_TRANSPORT`) | `healthy`، `tls_failed`، `ws_rejected` |
| `frp` | فقط `systemctl is-active frpc` | `healthy`، `dead` |
| `noise` (و بقیه) | probe واقعی ندارد | همیشه `healthy` |

نتیجه‌ی هر probe با فیلدهای `latency_ms` و `consecutive_failures` ذخیره می‌شود.

> ⚠️ برای `noise` هیچ probe واقعی‌ای وجود ندارد؛ بنابراین adaptive نمی‌تواند اختلال این حامل را تشخیص دهد. برای حامل‌های `plain`/`backhaul`/`frp`/`noise` هم کنترلر سوئیچ خودکار انجام نمی‌دهد (پایین را ببینید).

---

## پارامترها و آستانه

```bash
ratholenode adaptive on [--interval N] [--failures N] [--recoveries N]
```

| پارامتر | پیش‌فرض | توضیح |
|---------|---------|-------|
| `--interval` | ۳۰ ثانیه | بازه‌ی بین هر probe (به `rathole-adaptive.timer` می‌رود) |
| `--failures` | ۳ | تعداد شکست متوالی برای تصمیم به سوئیچ |
| `--recoveries` | ۵ | تعداد probe سالم متوالی WSS برای بازگشت از KCP، پس از پایان cooldown |

**Cooldown:** مقدار `ADAPTIVE_COOLDOWN` در `/etc/rathole/adaptive.env` با پیش‌فرض ۳۰۰ ثانیه، فاصلهٔ حداقل بین دو تغییر carrier است. برای جلوگیری از نوسان، در این فاصله تغییر جدید انجام نمی‌شود. مقدار صفر این فاصله را غیرفعال می‌کند.

**قفل اجرا:** کنترلر با `flock` روی `/run/rathole-adaptive.lock` اجرا می‌شود تا دو دور هم‌زمان با هم تداخل نکنند.

---

## رفتار کنترلر (مهم)

```bash
ratholenode adaptive run     # همان چیزی که timer صدا می‌زند
```

- اگر `ADAPTIVE_ENABLED=1` باشد و `TUNNEL` فعلی `ws` باشد، با رسیدن `consecutive_failures` به آستانه به `kcp` سوئیچ می‌کند؛ اگر حامل فعلی `kcp` باشد و probe آن شکست بخورد، به `ws` برمی‌گردد.
- روی KCP، پس از تعداد `ADAPTIVE_RECOVERIES` پاسخ سالم متوالی از WSS و پایان cooldown به WSS بازمی‌گردد. پیش از هر تغییر، سلامت حامل جایگزین بررسی می‌شود و شکست تولید کانفیگ یا reload با بازگشت به حالت قبلی گزارش می‌شود.
- **کنترلر فقط بین `ws` و `kcp` سوئیچ می‌کند.** اگر حامل فعلی `plain`، `noise`، `backhaul`، `frp` یا `gre` باشد، هشدار می‌دهد که «حامل دست‌ساز/کانونی است» و **هیچ تغییر خودکاری انجام نمی‌دهد**.
- به همین دلیل **انتخاب دستی حامل همیشه بر adaptive اولویت دارد**: اگر با کنترل‌های سرویس هاب یا CLI حامل را عوض کنید، adaptive آن را برنمی‌گرداند.
- `plain` هرگز به‌صورت خودکار انتخاب نمی‌شود (حتی با `ALLOW_INSECURE=1`)؛ در نسخه‌ی فعلی کنترلر آن را در چرخش قرار نمی‌دهد.

---

## دستورات مدیریت

```bash
# روشن کردن (env + systemd timer)
sudo ratholenode adaptive on --interval 30 --failures 3 --recoveries 5

# وضعیت جاری (حامل فعال + نتیجه آخرین probe)
sudo ratholenode adaptive status

# اجرای یک probe آنی
sudo ratholenode adaptive test
sudo ratholenode adaptive test --json

# اجرای یک دور کنترلر (debug)
sudo ratholenode adaptive run

# خاموش کردن (حالت فعلی حفظ می‌شود)
sudo ratholenode adaptive off
```

`adaptive status` خلاصه‌ی `classification`، `latency_ms` و `consecutive_failures` آخرین probe را چاپ می‌کند. `adaptive test --json` فایل state را خام می‌ریزد.

---

## امنیت و حریم خصوصی

فایل state در `/etc/rathole/adaptive-state.json` (mode 0600) فقط این فیلدها را نگه می‌دارد:

```
time, current, classification, latency_ms, consecutive_failures
```

هیچ‌کدام از `token`، `CONTROL_PATH` یا کلیدهای رمزنگاری در این فایل ثبت یا از طریق API هاب فاش نمی‌شوند. تنظیمات در `/etc/rathole/adaptive.env` (mode 0600) نگه‌داری می‌شوند.

---

## پیش‌نیاز

برای کارکرد سوئیچ خودکار، دو حامل `ws` و `kcp` باید آماده باشند:

```bash
# سمت ایران — KCP را فعال کن:
sudo ratholectl kcp on

# سمت نود — KCP را اضافه کن:
sudo ratholenode kcp on <ip:port> <key> [profile]

# سپس adaptive را روشن کن:
sudo ratholenode adaptive on
```

پروفایل KCP دو طرف باید یکی باشد (`balanced` / `lossy` / `aggressive`) و پورت UDP در فایروال هر دو سمت باز باشد.

---

## ارتباط با Watchdog

Watchdog (اگر روشن باشد) برای **lane اصلی** از همان probe استفاده می‌کند:

- `WD_PROBE=1` (پیش‌فرض) probe را روی lane اصلی اجرا می‌کند و **state مربوط به adaptive را بازنویسی نمی‌کند**.
- فقط وقتی `WD_PROBE_FAILS` (پیش‌فرض ۳) probe متوالی ناموفق باشد تانل را restart می‌کند — برای جلوگیری از restart تانل سالم در اثر jitter کوتاه.
- `ratholenode watchdog on [interval]` / `off` / `status`.

جزئیات عیب‌یابی: **[Troubleshooting](Troubleshooting)**.
