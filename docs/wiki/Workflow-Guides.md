# راهنماهای عملی (Workflow Guides)

سناریوهای رایج گام‌به‌گام. هر بخش مستقل است — فقط بخشی را بخوانید که نیاز دارید.

---

## ۱. راه‌اندازی دسترسی direct-IP

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

## ۲. مهاجرت به Backhaul (SMUX)

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
sudo ratholenode backhaul rm-svc trk01      # حذف از lane بک‌هال روی نود
# اگر سرویس دیگری در بک‌هال نیست:
sudo ratholenode backhaul off
```

---

## ۳. اضافه کردن دامنه دوم

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

## ۴. اتصال نود به چند سرور ایران (Multi-Upstream)

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
