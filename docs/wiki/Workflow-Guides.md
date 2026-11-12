# راهنماهای عملی (Workflow Guides)

سناریوهای رایج گام‌به‌گام. هر بخش مستقل است — فقط بخشی را بخوانید که نیاز دارید.

---

## ۱. راه‌اندازی REST Agent برای یک سرور (مدیریت بدون SSH)

**هدف:** هاب بتواند یک سرور ایران یا نود را بدون کلید/رمز SSH و از طریق API توکن‌دار مدیریت کند.

**پیش‌نیاز:** سرور با `install-panel.sh`/`install-node.sh` نصب شده باشد (فایل‌های agent از قبل در `/usr/local/share/rathole/` هستند) و پورت انتخابی از هاب در دسترس باشد.

### روی سرور ایران:

```bash
# پورت پیش‌فرض 8089؛ توکن در /etc/rathole-agent/token ساخته/خوانده می‌شود
sudo install-agent.sh --role iran --port 8089
# یا از خود CLI:
sudo ratholectl agent on 8089

# خروجی: API URL و Token را کپی کنید
sudo ratholectl agent show
```

### روی نود خارج:

```bash
sudo install-agent.sh --role node --port 8089
# یا:
sudo ratholenode agent on 8089
sudo ratholenode agent show
```

### تست بدون توکن (فقط ping):

```bash
curl -s http://<server_ip>:8089/api/ping
# → {"ok":true,"role":"iran","version":"1.0.0","hostname":"..."}
```

### ثبت در هاب:

1. داشبورد → Add server → فیلد Connection را روی **Agent REST API** بگذارید.
2. `API URL` = `http://<public_ip>:8089` (یا `https://<domain>:8089` اگر TLS دارید).
3. `Token` = همان توکن agent.
4. اگر HTTPS با گواهی self-signed است، در سمت هاب `RATHOLE_AGENT_INSECURE_SSL=1` بگذارید یا `insecure_ssl: true` را در رکورد همین سرور داخل `inventory.json` ست کنید (فرم UI فیلد جدا ندارد).
5. برای نود/سرورهایی که GRE استفاده می‌کنند، فیلد `public_ip` را هم درست بدهید تا IPهای GRE خودکار تشخیص داده شوند.

### چک‌لیست:

```bash
sudo journalctl -u rathole-agent -n 30 --no-pager   # سرویس سالم؟
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8089/api/ping   # 200
sudo ratholectl agent status                        # active + توکن
```

اگر هاب `no_agent` نشان داد، پورت/فایروال و `api_url` را بررسی کنید. جزئیات خطاها: **[Troubleshooting](Troubleshooting)**.

---

## ۲. تغییر حامل یک سرویس با کنترل‌های سرویس (و همگام‌سازی دو سمت)

**هدف:** حامل یک سرویس (مثلاً `trk01`) را عوض کنید، بدون تغییر path کاربر و پورت inbound.

**پیش‌نیاز:** سرویس روی سرور ایران و نود خارج ثبت شده باشد و هاب هر دو سرور را ببیند.

### گام‌ها (در پنل هاب):

1. صفحه‌ی سرور ایران (یا صفحه‌ی نود) → در ردیف سرویس `trk01` روی **«حامل و پروتکل»** بزنید.
2. در مودال این فیلدها را پر کنید:
   - **سرور نود خارجی** — اگر نود به‌طور یکتا پیدا شود خودکار پر می‌شود.
   - **حامل جدید** — `ws`، `kcp`، `plain`، `noise`، `backhaul`، `frp`، `gre` یا `فرپ+گری` (`frp+gre`).
   - **IP عمومی ایران** — برای `noise`/`frp`/`kcp`/`gre` و حالت‌های direct-IP.
   - **IP عمومی نود** — برای `gre`/`frp+gre`.
   - **آدرس مجازی GRE** — پیش‌فرض `10.10.10.1` در ساب‌نت `/30` (سمت نود خودکار `x.x.x.2` می‌شود).
   - **ترانسپورت FRP** / **ترانسپورت Backhaul** / **پروفایل KCP-Backhaul** — در صورت نیاز.
   - **پورت اختصاصی حامل در ایران** — اختیاری (پیش‌فرض: FRP=7000، BH=3080، Plain=8880، Noise=2334).
3. تأیید کنید. UI به‌طور خودکار **هر دو سمت** را تنظیم می‌کند:
   - اگر حامل سمت ایران فعال نباشد، اول فعالش می‌کند (`kcp_on`/`noise_on`/`backhaul_on`/`frp_on`/`plain_on`/`gre_on`).
   - برای `noise`/`backhaul`/`frp` نود را سمت ایران به آن مسیر می‌برد (`noise_node_on`/`backhaul_node_on`/`frp_node_on`).
   - سرویس را در رجیستری درست ثبت می‌کند: سرویس‌های Backhaul در `bh-services.conf` و بقیه در `services.conf`.
   - پارامترهای اتصال را از خود سرور ایران می‌گیرد (token/inbound/pubkey/کنترل‌پت) — لازم نیست دستی کپی کنید.
4. بعد از اعمال: **«تست سلامت»** بزنید و برچسب حامل را چک کنید (مثلاً `KCP / UDP · balanced` یا `Backhaul / WSMUX`).

### نکات مهم:

- **پورت inbound تغییر نمی‌کند:** تغییر حامل پورت موجود را از وضعیت تازه‌ی ایران می‌خواند؛ نگاشت `127.0.0.1:<iran_port>` و اینباند نود ثابت می‌ماند.
- **تراکنش کامل نیست:** اگر یک مرحله شکست بخورد، UI نتیجه‌ی ناقص را اعلام و وضعیت را دوباره می‌خواند (برای `noise`/`frp` وقتی حامل قبلی `ws` بوده، تلاش rollback هم انجام می‌شود). لاگ/خطا را ببینید و اگر لازم بود مرحله را تکرار کنید.
- **حامل اصلی مشترک است:** سرویس‌های lane رتهول یک نود، حامل و شنونده‌ی مشترک ایران دارند؛ تغییر پورت حامل مشترک ممکن است روی سایر سرویس‌های همان نود هم اثر بگذارد.
- **Game/SNI:** برای این سرویس‌ها دکمه‌های حامل/کانفیگ پیام راهنما می‌دهند؛ مدیریت آن‌ها در بخش «سرویس‌های گیمینگ (SNI/443)» است.

### اگر پنل در دسترس نیست (همان کار با CLI):

```bash
# KCP
sudo ratholectl kcp on 443 balanced
sudo ratholenode kcp on <iran_ip>:443 <key> balanced

# Noise
sudo ratholectl noise on 2334
sudo ratholectl noise node trk01 on
# pubkey را از ratholectl noise show بردارید:
sudo ratholenode noise on <iran_ip>:2334 <pubkey>

# Backhaul
sudo ratholectl backhaul on 3080 wsmux balanced
sudo ratholectl backhaul node trk01 on
# خط آماده را از ratholectl backhaul show بگیرید:
sudo ratholenode backhaul on <domain> <bh_token> wssmux balanced
sudo ratholenode backhaul add-svc trk01 <bh_token> <inbound_port>

# FRP (اگر هسته روشن نیست، روی ایران `frp on 7000 quic` توکن را خودکار می‌سازد؛ با `ratholectl frp show` بخوانید)
sudo ratholectl frp on 7000 quic
sudo ratholectl frp node trk01 on
sudo ratholenode frp on <iran_ip>:7000 <frp_token> quic <remote_port>

# برگشت به WebSocket/443
sudo ratholenode plain off
sudo ratholenode kcp off        # اگر KCP فعال بوده
sudo ratholectl kcp off         # فقط اگر نود دیگری از KCP استفاده نمی‌کند
```

> پس از هر تغییر، `ratholenode status` و `ratholenode adaptive test` را بزنید و برچسب پروتکل را در هاب refresh کنید. `?` یعنی پروتکل گزارش نشده (نه لزوماً قطع).

---

## ۳. مهاجرت Backhaul ↔ Noise

**هدف:** یک سرویس را بین دو لین پرترافیک/امن جابه‌جا کنید. هر دو حامل مسیر عمومی و inbound را حفظ می‌کنند و سرویس فقط بین دو رجیستری جابه‌جا می‌شود.

### Backhaul → Noise:

1. در ردیف سرویس → **«حامل و پروتکل»** → حامل `noise` → تأیید.
2. UI سمت ایران `noise on` (اگر لازم) + `noise_node_on` را می‌زند، سمت نود `noise_on` با pubkey گرفته‌شده از ایران، سپس سرویس را از `bh-services.conf` خارج و در `services.conf` ثبت می‌کند.
3. اگر آخرین سرویس lane بک‌هال بود، کلاینت بک‌هال نود خاموش می‌شود؛ lane رتهول روشن می‌ماند.

### Noise → Backhaul:

1. همان مودال → حامل `backhaul` → ترانسپورت (`wssmux` پیشنهادی) و پروفایل (`balanced`/`lossy`/`aggressive`) را انتخاب کنید.
2. UI `backhaul on`/`backhaul_node_on` سمت ایران و `backhaul_on` + `add_bh_svc` سمت نود را می‌زند و سرویس را از `services.conf` به `bh-services.conf` منتقل می‌کند.

### چک‌لیست پس از مهاجرت:

```bash
# ایران
sudo ratholectl noise status
sudo ratholectl backhaul status
# نود
sudo ratholenode noise status
sudo ratholenode backhaul status
sudo ratholenode backhaul ls
sudo ratholenode ls
sudo journalctl -u rathole-backhaul-client -n 20 --no-pager
```

**نکته‌ی توکن:** توکن Backhaul از توکن سرویس جداست؛ اگر با CLI دستی مهاجرت می‌کنید، همان `bh_token` که ایران چاپ می‌کند را به نود بدهید.

---

## ۴. مهاجرت به Backhaul (SMUX) — روش CLI

**هدف:** سرویس `trk01` را روی lane بک‌هال (مالتی‌پلکس SMUX) قرار دهید، در حالی که lane رتهول می‌تواند برای سرویس‌های دیگر همان ماشین روشن بماند.

**پیش‌نیاز:** Backhaul هر سرور ایران یک client خارجی دارد (کنترل 1:1)، اما همان client می‌تواند چند سرویس را از `bh-services.conf` حمل کند.

### روی سرور ایران:

```bash
# ۱. هسته backhaul را فعال کن
sudo ratholectl backhaul on 3080 wsmux balanced

# ۲. مالکیت مسیر trk01 را به backhaul بده
sudo ratholectl backhaul node trk01 on

# ۳. دستور آماده نود را ببین
sudo ratholectl backhaul show
# → خطی مثل: ratholenode backhaul on domain.com <token> wssmux balanced
```

### روی نود خارج:

```bash
# دقیقاً همان خطی که 'show' چاپ کرد:
sudo ratholenode backhaul on <domain> <token> wssmux balanced

# همان سرویس را در registry مستقل Backhaul ثبت کن؛ token باید BH_TOKEN باشد:
sudo ratholenode backhaul add-svc trk01 <token> <inbound_port>

# سرویس‌های باقی‌مانده در services.conf همچنان از rathole-client عبور می‌کنند.
```

**چک‌لیست پس از مهاجرت:**
```bash
sudo ratholectl backhaul status   # ایران: سرویس فعال؟
sudo ratholenode backhaul status  # نود: client و تعداد سرویس‌های lane
sudo ratholenode backhaul ls      # registry بک‌هال
sudo journalctl -u rathole-backhaul-client -n 20   # نود: خطای اتصال؟
```

**برگشت به WebSocket:**
```bash
sudo ratholectl backhaul node trk01 off   # ایران
sudo ratholenode backhaul rm-svc trk01     # حذف از lane بک‌هال روی نود
# اگر سرویس دیگری در بک‌هال نیست:
sudo ratholenode backhaul off
```

---

## ۵. راه‌اندازی دسترسی direct-IP

**هدف:** کاربران بتوانند مستقیم با IP سرور ایران (بدون دامنه، بدون TLS) وصل شوند.

**پیش‌نیاز:** سرور ایران با یک نود حداقل نصب و فعال.

### روی سرور ایران:

```bash
# فعال‌سازی listener
sudo ratholectl direct on --port 8081 --header X-Cdn-Id

# باز کردن پورت در فایروال
sudo ufw allow 8081/tcp

# مشاهده دستور آماده برای هر نود
sudo ratholectl direct show trk01
```

### کانفیگ Xray کاربر:

| فیلد | مقدار |
|------|-------|
| address | `<IP_ایران>` |
| port | `8081` |
| transport | WebSocket |
| TLS | ❌ |
| path | `/trk01` |
| header | `X-Cdn-Id: trk01` |
| host | هر چیزی (decoy، مثلاً `myket.ir`) |

**نکات مهم:**
- هدر یک routing hint است، نه credential — هر کسی که نام نود را بداند می‌تواند به inbound آن برسد (که خودش auth دارد)
- اگر `direct_port == plain_port` باشد، هر دو روی یک پورت کار می‌کنند
- نودهای game/SNI از direct-IP پشتیبانی نمی‌کنند

---

## ۶. اضافه کردن دامنه دوم

**هدف:** یک دامنه اضافی روی همان سرور ایران داشته باشید — مثلاً برای کاربرانی که دامنه اصلی برایشان کار نمی‌کند.

### با certbot (گواهی از Let's Encrypt):

```bash
# DNS دامنه جدید باید به همین سرور اشاره کند
sudo ratholectl domain add cdn.example.ir --certbot [--email admin@example.ir]
```

### با گواهی آماده:

```bash
sudo ratholectl domain add cdn.example.ir \
  --fullchain /etc/letsencrypt/live/cdn.example.ir/fullchain.pem \
  --key /etc/letsencrypt/live/cdn.example.ir/privkey.pem
```

### برای Cloudflare (CNAME، TLS از CF):

```bash
# نیازی به گواهی جداگانه نیست — از گواهی دامنه اصلی استفاده می‌شود
sudo ratholectl domain add cdn.example.ir
# اگر گواهی پیدا نشود از گواهی اصلی استفاده می‌کند (warning می‌دهد)
```

### مشاهده و حذف:

```bash
sudo ratholectl domain ls
sudo ratholectl domain rm cdn.example.ir
```

### تغییر دامنه اصلی:

```bash
sudo ratholectl domain primary newprimary.example.ir --certbot
```

---

## ۷. اتصال نود به چند سرور ایران (Multi-Upstream)

**هدف:** یک نود خارج به چند سرور ایران همزمان وصل شود — هر کدام سرویس‌های مستقل دارند.

### سناریو:
- سرور ایران اصلی (`main`): `iran1.example.ir:443`، سرویس `trk01`
- سرور ایران دوم (`iran2`): `iran2.example.ir:443`، سرویس `nld01`

### روی نود خارج:

```bash
# تانل اصلی (main) — قبلاً نصب شده
sudo ratholenode status   # confirm main is connected

# اضافه کردن سرور دوم به عنوان upstream
sudo ratholenode upstream add iran2 iran2.example.ir:443

# اضافه کردن سرویس از سرور دوم
sudo ratholenode upstream add-svc iran2 nld01 <token_from_iran2> 2088

# بررسی وضعیت
sudo ratholenode upstream status iran2
sudo ratholenode upstream ls
```

### KCP برای هر upstream:

```bash
# روی سرور ایران دوم:
sudo ratholectl kcp on

# روی نود:
sudo ratholenode migrate                                     # نقشه راهنما چاپ می‌کند
sudo ratholenode upstream kcp iran2 on <IP2>:443 <KEY2> balanced
```

### بررسی همه upstreamها:

```bash
sudo ratholenode upstream ls        # لیست + transport جاری هر کدام
sudo ratholenode logs all           # لاگ main + همه upstreamها
```

### حذف upstream:

```bash
sudo ratholenode upstream rm iran2
```

---

## ۸. آپدیت از مخزن خصوصی

**هدف:** سروری که از یک fork خصوصی نصب شده را به آخرین نسخه آپدیت کنید (بدون دسترسی عمومی به release).

### گزینه ۱ — `tools/update-private.sh` (روی خود سرور):

```bash
# توکن را مخفی می‌پرسد؛ یا از env بخوانید
sudo RATHOLE_GH=owner/repo bash tools/update-private.sh

# اگر نمی‌خواهید از latest استفاده کنید، main یا tag مشخص بدهید
sudo RATHOLE_GH=owner/repo RATHOLE_RELEASE=main bash tools/update-private.sh
sudo RATHOLE_GH=owner/repo RATHOLE_RELEASE=v2.0.2 bash tools/update-private.sh

# یا توکن از محیط (بدون prompt):
sudo RATHOLE_GH=owner/repo RATHOLE_GH_TOKEN=<PAT> bash tools/update-private.sh
```

اسکریپت برای `main` از API تاربال و Package استفاده می‌کند و برای release از assetهای `bootstrap.sh` + bundle؛ سپس همان مسیر امن `bootstrap.sh --local … --update` را اجرا می‌کند (snapshot + health-check + rollback خودکار). توکن در پایان از محیط unset می‌شود.

### گزینه ۲ — نصب/آپدیت یک‌خطی با توکن:

برای مخزن خصوصی خود فایل `install.sh` را با هدر توکن بگیرید (raw بدون توکن ۴۰۴ می‌دهد):

```bash
curl -fsSL -H "Authorization: Bearer <PAT>" \
  https://raw.githubusercontent.com/owner/repo/main/install.sh -o /tmp/install.sh
sudo RATHOLE_GH=owner/repo bash /tmp/install.sh --token <PAT> --release v2.0.2 --update
```

### نکات:

- توکن باید `Contents: read` داشته باشد؛ برای mirrorهای عمومی ghproxy در مخزن خصوصی استفاده نمی‌شود.
- **آپدیت گروهی هاب** برای مخزن خصوصی پشتیبانی نمی‌شود (هاب روی سرور به توکن GitHub دسترسی ندارد)؛ روی هر سرور جدا اجرا کنید.
- اگر health-check شکست بخورد، `update.sh` خودکار به snapshot قبل برمی‌گردد؛ جزئیات در **[Troubleshooting](Troubleshooting)**.
