# شروع سریع — نصب تعاملی در ۵ مرحله

این صفحه **کوتاه‌ترین مسیر تا یک سیستم کارکننده** است: یک دستور، چند سؤال، تمام.
اگر دنبال نصب دستی/سفارشی‌سازی هستی، به [راهنمای نصب کامل](install-manual.fa.md) برو.

!!! tip "مختصر مفید"
    رویسرور ایران فقط این را بزن و به سؤال‌ها جواب بده:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
      | sudo bash
    ```

---

## ۰) پیش‌نیازها

| مورد | نیاز |
|---|---|
| سیستم‌عامل | Ubuntu 22.04 / 24.04 (یا Debian 12) |
| دسترسی | `root` (یا `sudo`) |
| پورت | `443/tcp` آزاد روی سرور ایران |
| دامنه | یک دامنه که به IP سرور ایران اشاره کند (مثلاً `panel.example.ir`) |
| گواهی TLS | فایل `fullchain.pem` و `privkey.pem` (یا در نصب با certbot بگیر) |
| سرور خارج | یک VPS بیرون ایران برای نقش «نود» (اختیاری، هر زمان اضافه می‌شود) |

!!! note "چرا گواهی لازم است؟"
    تمام کاربران روی `https://domain` وصل می‌شوند و nginx تنها جایی است که TLS را ترمینیت می‌کند.
    اگر گواهی نداری، در مرحلهٔ نصب جواب `y` به certbot بده تا خودش بگیرد.

---

## ۱) نصب پنل ایران (۵ دقیقه)

روی **سرور ایران**:

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash
```

### چه چیزهایی می‌پرسد؟

**الف) نسخه:**

```text
kodam noskhe nasb shavad?
  - Enter        → latest (akharin noskhe-ye paydar — tosiye)
  - yek tag      → masalan v1.8.0 (noskhe-ye khas-e montasher-shode)
  - beta         → akharin pre-release (azmayeshi)
entekhab [latest]:
```

→ فقط **Enter** بزن.

**ب) حالت نصب:**

```text
halat nasb ra entekhab kon:
  1) panel (server Iran)
  2) node (server kharej)
  3) update (beroozresani kamel ba snapshot + rollback-e khodkar)
  4) fght amade-sazi (bedoon ejra-ye nasab)
  5) rollback (bazgasht be akharin snapshot-e ghabl az update)
  6) list-e backup-ha (snapshot-haye mojood)
  7) hazf kamel (uninstall — panel/node/hub + config/state)
entekhab [1/2/3/4/5/6/7]:
```

→ روی سرور ایران **`1`** بزن.

**ج) تنظیمات اولیه (`ratholectl init`)** — فقط دو سؤال اول مهم‌اند:

```text
damnh (masalan btli.ir):  panel.example.ir
masir fullchain.pem [/root/cert/panel.example.ir/fullchain.pem]:
masir privkey.pem   [/root/cert/panel.example.ir/privkey.pem]:
file config nginx baraye tvlid/riplis [/etc/nginx/conf.d/rathole.conf]:
port kontroli lvkal rathole [2333]:
port sait fik/panel (default) [8080]:
port sabaskripshn [2096]:
shrva shmarh port dita [1001]:
shrva shmarh port mdirit(api) [7001]:
```

- **دامنه** را بنویس، و اگر گواهی در مسیر پیشفرض نیست، مسیرش را بده.
- بقیه را **Enter** بزن (پیش‌فرض‌ها درست‌اند).
- اگر گواهی پیدا نشود: `ba certbot grfth shvd? [y/N]` → اگر دامنه به این سرور وصل است `y` بزن.

!!! warning "اگر گواهی نداری و certbot هم نمی‌خواهی"
    نصب ادامه می‌یابد ولی nginx تا وقتی گواهی نگذاری بالا نمی‌آید. بعداً با
    `ratholectl cert <domain>` یا `ratholectl set fullchain <path>` درستش کن.

---

## ۲) بررسی نصب

```bash
sudo ratholectl status     # داشبورد: دامنه، پورت‌ها، گواهی، سرویس‌ها، نودها
sudo ratholectl doctor     # چک سلامت (همه باید ✓ باشند)
sudo ratholectl paths      # مسیر همهٔ فایل‌ها با ✓/✗
```

انتظار: `rathole-server: active`، `nginx: active`، گواهی معتبر، و `doctor` بدون خطا.

---

## ۳) افزودن نود (روی پنل ایران)

یک نام و یک پورت اینباند انتخاب کن (نام = همان path عمومی):

```bash
sudo ratholectl add trk01 2087
```

خروجی، یک دستور آمادهٔ نصب برای همان نود چاپ می‌کند:

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash -s -- --node -- \
    --server panel.example.ir:443 --name trk01 \
    --token <TOKEN> --inbound-port 2087
```

> اگر خواستی دوباره ببینی: `sudo ratholectl show trk01`

### روی سرور خارج

همان دستور را بزن — یا اگر تعاملی می‌خواهی:

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash
# مرحلهٔ «حالت نصب» → 2 (node)
```

و به این سؤال‌ها جواب بده:

```text
adres server Iran (masalan panel.example.ir:443):  panel.example.ir:443
name node (masalan trk01):                         trk01
token service:                                     <TOKEN از پنل>
port inbound Xray rooye node [2087]:               2087
token API (akhtiari, khali=rad):                   ← Enter
```

---

## ۴) تست نهایی

روی **پنل ایران**:

```bash
sudo ratholectl ls        # نود trk01 باید با وضعیت سالم دیده شود
sudo ratholectl doctor    # چک نهایی
```

روی **نود**:

```bash
sudo ratholenode status
sudo ratholenode logs 50
```

مسیر کاربر: `https://panel.example.ir/trk01` → از nginx به تونل و سپس به Xray روی نود می‌رسد.

---

## ۵) هاب مرکزی (اختیاری)

اگر چند سرور ایران/نود داری و می‌خواهی همه را از یک پنل وب مدیریت کنی:

```bash
sudo ratholectl hub on 8088     # نصب + روشن‌کردن هاب پشت nginx
sudo ratholectl hub auto-add    # ثبت همین سرور در inventory
sudo ratholectl hub status
```

سپس: `https://panel.example.ir/hub/` — و اگر SSH نمی‌خواهی، روی هر سرور:

```bash
sudo install-agent.sh --role iran|node   # مدیریت از طریق REST Agent (پورت 8089)
```

---

## عیب‌یابی سریع

| نشانه | علت رایج | راه‌حل |
|---|---|---|
| `nginx -t` خطا می‌دهد | گواهی اشتباه/مسیر غلط | `ratholectl paths` → مسیر `fullchain`/`key` را درست کن، بعد `ratholectl regen` |
| `rathole-server` بالا نمی‌آید | پورت `2333` اشغال است | `ratholectl set control-port 2334` و `ratholectl regen` |
| نود وصل نمی‌شود | توکن/آدرس یا پورت ۴۴۳ | `ratholenode logs 100` و توکن را دوباره از `ratholectl show <name>` بگیر |
| `/trk01` صفحهٔ فیک نشان می‌دهد | نود وصل نیست | `ratholectl doctor`؛ وضعیت نود در `ratholectl ls` |
| گواهی منقضی شده | رenew نشده | `ratholectl certs` و سپس `ratholectl cert <domain>` |

مشکل حل نشد؟ [عیب‌یابی کامل](wiki/Troubleshooting.md) · [راهنمای نصب دستی](install-manual.fa.md)

---

## نصب غیرتعاملی (برای اسکریپت/CI)

اگر نمی‌خواهی هیچ سؤالی پرسیده شود، همه‌چیز را با پرچم بده:

```bash
# سرور ایران
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash -s -- --panel \
    --domain panel.example.ir \
    --fullchain /root/cert/panel.example.ir/fullchain.pem \
    --key       /root/cert/panel.example.ir/privkey.pem

# نود خارج (توجه: آرگومان‌های نود بعد از -- می‌آیند)
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash -s -- --node -- \
    --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087
```

نسخهٔ خاص: `--release v2.0.3` · بتا: `--beta` · پایدار: `--stable`
(متغیر محیطی `RATHOLE_GH=owner/repo` مخزن را عوض می‌کند.)