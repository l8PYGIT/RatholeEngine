<div align="center">

<img src="assets/logo.svg" alt="RatholeEngine" width="120" height="120" />

# RatholeEngine

**سیستم تونل معکوس چند-موقعیتی روی rathole + Nginx**

_یک پورت (۴۴۳) · یک دامنه · یک گواهی · مسیریابی نودها با path_
_ساخته‌شده برای تونل مقاومِ سانسور به داخل ایران._

[![CI](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/ci.yml/badge.svg)](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/l8PYGIT/RatholeEngine?sort=semver&color=7c3aed)](https://github.com/l8PYGIT/RatholeEngine/releases/latest)
[![License](https://img.shields.io/github/license/l8PYGIT/RatholeEngine?color=blue)](../LICENSE)
[![Stars](https://img.shields.io/github/stars/l8PYGIT/RatholeEngine?style=flat&color=16a34a)](https://github.com/l8PYGIT/RatholeEngine/stargazers)
<br/>
![shell](https://img.shields.io/badge/shell-bash-4EAA25?logo=gnubash&logoColor=white)
![python](https://img.shields.io/badge/python-stdlib%20only-3776AB?logo=python&logoColor=white)
![tunnel](https://img.shields.io/badge/tunnel-rathole%20%2B%20nginx-7c3aed)

[**English**](../README.md) · [**فارسی**](#این-چیست) · [**ویکی جامع (Wiki)**](https://github.com/l8PYGIT/RatholeEngine/wiki) · [شروع سریع](#شروع-سریع) · [Telegram](https://t.me/l8PY4NET)

</div>

<div dir="rtl">

## این چیست

مدیریت خودکار تونل ریورس مولتی‌لوکیشن با **rathole + Nginx** روی **یک پورت (۴۴۳) و یک دامنه و یک گواهی**.
ساخته‌شده برای سناریوی: پنل (ایران) = rathole **server** + nginx، و نودهای خارج = rathole **client**.
مسیریابی به نودها با **path** انجام می‌شود (دقیقاً مدل `map $uri $backend_port`).

![نمای معماری](assets/architecture.svg)

*نمای کلی معماری — همه‌چیز روی یک پورت/دامنه پشت Nginx؛ نودهای خارج با تونل ریورس به سرور ایران وصل می‌شوند.*


```
کاربر ──TLS/443──► nginx (btli.ir)
                     ├── /            (بدون upgrade) → 8080  سایت فیک
                     ├── /  + ws      → 2333  کانال کنترلی rathole
                     ├── /sub/...     → 2096  ساب‌اسکریپشن
                     ├── /trk01       → 1001  دیتای نود trk01 ─┐
                     ├── /nld01       → 1002  دیتای نود nld01 ─┼─ تونل rathole ─► نودهای خارج
                     └── ...                                   ┘
```

## اجزاء

| فایل | محل اجرا | کار |
|------|----------|-----|
| `bootstrap.sh` | هر سرور | آماده‌سازی محیط + دانلود بسته از لینک + باز کردن + اجرای نصاب |
| `install-panel.sh` | سرور **ایران** | نصب rathole، jq، nginx، نصب `ratholectl`، systemd، init اولیه |
| `ratholectl` | سرور **ایران** | مدیریت نودها؛ تولید خودکار `server.toml` و کانفیگ nginx؛ reload |
| `install-node.sh` | هر **نود خارج** | نصب rathole، نوشتن `node.env`، نصب `ratholenode`، استارت |
| `ratholenode` | هر **نود خارج** | مدیریت کلاینت در طول زمان + بررسی تداخل پورت با nginx نود |
| `ratholehub/install-hub.sh` | سرور **ایران** | نصب پنل هاب (`ratholectl hub on` بار اول خودکار اجرایش می‌کند) |
| `install-agent.sh` | ایران یا نود | نصب آژنت REST (`rathole-agent.service`) برای مدیریت بدون SSH |
| `update.sh` | هر سرور | آپدیت امن: snapshot + health-check + rollback خودکار |
| `uninstall-panel.sh` | سرور **ایران** | حذف کامل + ری‌استور بکاپ کانفیگ nginx |
| `uninstall-node.sh` | هر **نود خارج** | حذف کامل کلاینت (بدون دست‌زدن به nginx/Xray نود) |

## مدیریت در طول زمان (CLI)

### روی سرور ایران — `ratholectl`

```bash
ratholectl hub on [port]               # روشن‌کردن پنل هاب پشت nginx (پیش‌فرض 8088؛ بار اول خودکار نصب می‌شود)
ratholectl hub off                     # برداشتن location پنل از nginx (سرویس 127.0.0.1 روشن می‌ماند)
ratholectl hub status                  # آدرس https، پورت داخلی و وضعیت سرویس ratholehub
ratholectl hub auto-add                # ثبت خودکار همین سرور ایران در inventory هاب
ratholectl ls                          # لیست نودها
ratholectl add <name> <inbound> [--api-port N]
ratholectl edit <name> --inbound 2088  # تغییر پورت اینباند نود
ratholectl edit <name> --api-port 62050 # روشن‌کردن کانال مدیریت
ratholectl edit <name> --api-port off   # خاموش‌کردن کانال مدیریت
ratholectl rename <old> <new>          # تغییر نام/مسیر نود
ratholectl rotate <name>               # چرخش توکن(ها)
ratholectl show <name>                 # جزئیات + دستور نصب نود (curl یک‌خطی + install-node.sh)
ratholectl set domain <new>            # تغییر تنظیمات سراسری
ratholectl set fake-port 8443          # ... fake-port/sub-port/control-port/sub-path/hub-path/nginx-conf/fullchain/key
                                       # از Hub UI هم قابل ویرایش است (بخش Ports در صفحه سرور)
ratholectl rm <name>                   # حذف نود
ratholectl status [--json]             # داشبورد کامل وضعیت (دامنه/پورت‌ها/گواهی/سرویس‌ها/نودها) — مثل ساب‌پنل VPN
ratholectl paths                       # مسیر همه کانفیگ‌ها و فایل‌ها با علامت ✓/✗ وجود
ratholectl info                        # دامنه/گواهی/انقضا + دامنه‌های SNI
ratholectl certs                       # جدول همه گواهی‌ها: DOMAIN|EXPIRY|ACTIVE|SNI
ratholectl recover                     # بازگشت به حالت سالم تک‌دامنه‌ای (حذف دامنه‌های اضافی + regenerate)
ratholectl tune                        # BBR + لیمیت‌های سیستم/nginx (بدون ری‌استارت سرور)
ratholectl fakeweb start|stop|rm|status [port]   # سایت فیک پنل روی fake_port (پیش‌فرض 8080؛ اگر fake_port ست نشده باشد fallback: 8000)
ratholectl agent <on [port] [token]|off|status|token|show|restart>   # آژنت REST برای مدیریت بدون SSH (پیش‌فرض 8089)
ratholectl control-path <show|rotate [--dry-run]|clear>      # مسیر مخفی کانال کنترل (/_rh/<hex32>)
ratholectl doctor                      # بررسی سلامت
ratholectl version                     # نسخهٔ manager + rathole (manager_version=/rathole_version=)
ratholectl update                      # به‌روزرسانی کامل از GitHub (آخرین Release؛ snapshot + rollback خودکار)
ratholectl update beta                 # کانال بتا: آخرین pre-release (آزمایشی)
ratholectl update v2.0.2               # آپدیت به نسخه‌ی خاص
ratholectl menu                        # منوی تعاملی کامل
```

#### مدیریت چند دامنه

```bash
ratholectl domain add <domain> [--certbot] [--email E] [--fullchain F] [--key K]
# دامنه‌ی اضافی روی همان سرور؛ اگر گواهی ندارد از گواهی دامنه اصلی استفاده می‌کند (مناسب CNAME پشت Cloudflare)
ratholectl domain rm <domain>
ratholectl domain ls
ratholectl domain primary <domain> [--certbot|--fullchain F --key K]
# تغییر دامنه‌ی اصلی + گواهی

# دریافت گواهی Let's Encrypt با certbot (nginx را موقتاً می‌بندد):
ratholectl cert <domain> [email]

# گواهی self-signed برای ورود مستقیم به IP (بدون دامنه):
ratholectl ip-cert <IPv4> [days]       # پیش‌فرض ۸۲۵ روز
ratholectl ip-cert-show [IP]           # خروجی public cert (برای pin کردن روی نود)
ratholectl ip-cert-off                 # حذف vhost IP TLS
```

> **ip-cert + set-main:** وقتی گواهی self-signed برای IP ساختی، نود باید با `set-main` آن را به‌عنوان trusted root ثبت کند (ببین زیر بخش ratholenode).

هر تغییر، کانفیگ‌ها را بازتولید و سرویس‌ها را reload می‌کند.

> **نکتهٔ دستور نصب نود:** بعد از `ratholectl add <name> <inbound>` (و `ratholectl show <name>`)، **اول** یک دستور نصب آمادهٔ کپی به شکل curl یک‌خطی چاپ می‌شود که مستقیم روی نود خارج اجرا می‌شود، سپس شکل محلی `install-node.sh`:
> ```bash
> curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \
>   --server <panel>:443 --name <name> --token <T> --inbound-port <inbound>
> ```
> اگر دامنه‌ای ست نشده باشد (حالت تانل با IP)، `--server` با IP عمومی سرور پر می‌شود.

#### مسیر مخفی کانال کنترل (`control-path`)

کانال کنترلی rathole به‌طور پیش‌فرض روی مسیر `/` باز می‌شود؛ با coreهای جدید می‌توان همین مسیر را به یک مسیر مخفی (`/_rh/<32 hex>`) برد تا از DPI پسیو پنهان بماند:

```bash
ratholectl control-path show                 # مسیر فعلی (control_path=...؛ اگر ست نشده: /)
ratholectl control-path rotate --dry-run     # فقط نمایش مسیر جدید، بدون تغییر
ratholectl control-path rotate               # ساخت مسیر جدید + health-check + rollback خودکار
ratholectl control-path clear                # بازگشت به /
```

> بعد از `rotate` باید روی **هر نود** مسیر تازه را تنظیم کنی: `ratholenode control-path set '/_rh/...'` برای تونل اصلی و `ratholenode upstream control-path <id> set '/_rh/...'` برای هر سرور ایران اضافه. مسیر `/` همیشه کار می‌کند، پس نودهای به‌روزنشده قطع نمی‌شوند و می‌توانی نودها را یکی‌یکی منتقل کنی.

### سرویس game (SNI روی ۴۴۳ + TLS روی نود + گواهی واقعی)

برای یک سرویس امن‌تر/سبک‌تر کنار سیستم فعلی (مثلاً برای گیم) که با **SNI روی همان ۴۴۳** کار می‌کند و TLS را روی **نود** ترمینیت می‌کند (VLESS+TLS+Vision با گواهی واقعی):

```bash
# روی پنل ایران:
ratholectl game add gamenode 8444 game.l1t.ir   # نام، پورت اینباند TLS نود، ساب‌دامین(SNI)
ratholectl game cert game.l1t.ir                # گرفتن گواهی + دستور/محتوای انتقال به نود
ratholectl game ls
ratholectl game show gamenode                   # چاپ دستور نصب/تنظیم همین سرویس
ratholectl game rm gamenode
```
با اولین `game add`، پورت ۴۴۳ به حالت **stream/SNI** می‌رود و L7 فعلی (path/WS) روی پورت داخلی (۸۴۴۳) منتقل می‌شود — کاربران path هیچ تغییری نمی‌بینند. ترافیک `game.l1t.ir` به‌صورت L4 passthrough به نود می‌رود.

> برای یک upstream دلخواه که **قرار نیست از rathole رد شود** (سرویس/تونل مستقل خودت)، به‌جای `game` از [`proxy`](#۲۸-proxy--ریورس‌پروکسی-غیرتونلی-روی-همان-۴۴۳) استفاده کن: `ratholectl proxy add <name> <http(s)://host:port>`.

روی **نود**:
```bash
ratholenode add-svc gamenode <token> 8444    # توکن از خروجی game add
ratholenode fakeweb start 8081               # وب فیک سبک برای fallback
# سپس اینباند Xray = VLESS+TLS+Vision با گواهی /etc/xray-certs/game.l1t.ir/ و fallback→8081
```

> این حالت SNI↔IP منسجم دارد (game.l1t.ir → IP ایران)، گواهی واقعی، روی ۴۴۳، و سبک (L4). در برابر passive DPI منسجم‌تر از Reality با SNI قرضی است.

### روی هر نود خارج — `ratholenode`

```bash
ratholenode show                       # تنظیمات و سرویس‌های فعلی
ratholenode ls                         # لیست سرویس‌های روی این تونل
ratholenode add-svc <name> <token> <inbound>   # افزودن سرویس به همان تونل (توکن از 'ratholectl add' پنل)
ratholenode rm-svc <name>              # حذف سرویس
ratholenode set SERVER newdomain:443   # تغییر سرور (تانل اصلی/main)
ratholenode set-main <host:port> [tls_hostname] [trusted_root]
# تنظیم اتمیک سرور + SNI + CA سفارشی — برای اتصال به IP با گواهی self-signed:
# ratholenode set-main <ip>:443 <ip> /etc/rathole/trusted-<ip>.pem
ratholenode agent <on [port] [token]|off|status|token|show|restart>   # آژنت REST روی نود (پیش‌فرض 8089)
ratholenode control-path show               # مسیر مخفی کانال کنترل (پیش‌فرض /)
ratholenode control-path set <path>         # فقط بعد از rotate سمت ایران؛ restart + rollback خودکار
ratholenode control-path clear              # بازگشت به /
ratholenode adaptive on [--interval S] [--failures N] | off | status | test [--json]   # سوییچ خودکار ws↔kcp
ratholenode frp on <IRAN_IP:PORT> <TOKEN> [transport] [remote_port]   # transport: tcp|kcp|quic|websocket
ratholenode frp off | status                # بازگشت به ws/443 / وضعیت
ratholenode gre on <IRAN_IP> [tunnel_ip] [gre_name]   # پیش‌فرض tunnel_ip: 10.10.10.2
ratholenode gre status | off | probe <PEER_IP> [gre_name]   # probe = سنجش دسترسی peer روی اینترفیس gre
ratholenode fakeweb start|stop|rm|status [port]   # وب فیک سبک برای fallback (پیش‌فرض 8081)
ratholenode tune                            # BBR + لیمیت‌های سیستم
ratholenode doctor                          # سلامت node + پشتیبانی core از control-path
ratholenode check                      # بررسی تداخل پورت با nginx نود
ratholenode logs [n]                   # آخرین n خط لاگ تانل اصلی (پیش‌فرض ۵۰)
ratholenode logs all [n] [--bundle]    # لاگ تانل اصلی + همه upstreamها
ratholenode backup [file]              # snapshot از node.env + services + upstreamها
ratholenode restore <file>             # بازگردانی + بازتولید config + restart
ratholenode update                     # به‌روزرسانی کامل از GitHub (آخرین Release؛ snapshot + rollback خودکار)
ratholenode update beta                # کانال بتا: آخرین pre-release (آزمایشی)
ratholenode update v2.0.2              # آپدیت به نسخه‌ی خاص
ratholenode version                    # نسخهٔ manager + rathole
ratholenode status [--json] | logs | apply
```

#### Watchdog — راه‌اندازی مجدد خودکار تانل‌های گیرکرده

```bash
ratholenode watchdog on [interval_sec]   # پیش‌فرض ۶۰ ثانیه
# یک systemd.timer می‌سازد که periodically سرویس‌های تانل را بررسی می‌کند؛
# اگر service down باشد یا log پر از retry/connection error باشد، restart می‌کند.
ratholenode watchdog off
ratholenode watchdog status
```

#### حالت تطبیقی (`adaptive`) — سوییچ خودکار بین ws و kcp

اگر مسیر ناپایدار است و نمی‌خواهی هر بار دستی حامل را عوض کنی، یک تایمر systemd می‌سازد که هر چند ثانیه یک probe می‌زند و پس از چند شکست پیوسته، بین `ws` و `kcp` سوییچ می‌کند:

```bash
ratholenode adaptive on                        # interval=۳۰s، failures=3
ratholenode adaptive on --interval 20 --failures 2
ratholenode adaptive status                    # روشن/خاموش + آخرین classification و latency
ratholenode adaptive test [--json]             # یک probe فوری (healthy/tls_failed/tcp_timeout/ws_rejected/...)
ratholenode adaptive off                       # تایمر خاموش می‌شود؛ حامل فعلی حفظ می‌شود
```

> تایمر `rathole-adaptive.timer` نتیجهٔ هر probe را در `/etc/rathole/adaptive-state.json` ثبت می‌کند. سوییچ خودکار **فقط بین `ws` و `kcp`** انجام می‌شود؛ اگر حامل دستی دیگری (`plain`/`noise`/`backhaul`/`frp`/`gre`) انتخاب کرده باشی، دست‌نخورده می‌ماند. قبل از تکیه بر سوییچ خودکار، مسیر kcp را یک‌بار روی هر دو سمت (`ratholectl kcp on` و `ratholenode kcp on`) تنظیم کن تا مسیر جایگزین واقعاً وجود داشته باشد.

#### چند IP خروجی روی یک تونل (multi-egress)
اگر نود چند IP خروجی دارد و می‌خواهی همه روی **یک تونل** باشند:

1. روی **پنل** برای هر IP یک سرویس بساز:
   ```bash
   ratholectl add trk01-ip1 2087
   ratholectl add trk01-ip2 2088
   ratholectl add trk01-ip3 2089
   ```
2. روی **نود**، هر سرویس را با توکنش به همان تونل اضافه کن:
   ```bash
   ratholenode add-svc trk01-ip1 <token1> 2087
   ratholenode add-svc trk01-ip2 <token2> 2088
   ratholenode add-svc trk01-ip3 <token3> 2089
   ```
   همه زیر یک `[client]` → **یک کانال کنترلی (یک تونل)**.
3. در **Xray نود**، هر اینباند (path مربوطه) را به یک outbound با `sendThrough=IP` متفاوت route کن (انتخاب IP خروجی کارِ Xray است، نه rathole).

> **عدم تداخل با nginx روی نود:** کلاینت rathole **هیچ پورت عمومی‌ای bind نمی‌کند** (فقط اتصال خروجی)، پس با nginx روی نود تداخل ندارد. تنها قید: پورت اینباند Xray باید روی `127.0.0.1` و **غیر از 80/443** باشد. `ratholenode` این را هنگام `apply`/`check` بررسی می‌کند.

## پرفورمنس و استیبل‌سازی (لگ ریلز / مسیر lossy)

اگر مسیر ایران↔نود **پکت‌لاس** دارد (در iperf3 چیزی مثل ۹٪ UDP loss یا Retr بالای TCP)، علت لگ ریلز همین است: TCP داخل تونل، loss را با ارسال مجدد جبران می‌کند و throughput نوسانی/کند می‌شود (مشکل TCP-over-TCP). دو ابزار اضافه شده:

### ۱) `tune` — BBR و لیمیت‌های سیستم/nginx (بدون ری‌استارت سرور)
```bash
ratholectl tune      # روی ایران
ratholenode tune     # روی نود
```
BBR + fq + افزایش file/conntrack/backlog + worker_connections nginx. برست‌های ۵۰۲ زیر بار را هم کم می‌کند. فقط `sysctl --system` + `nginx reload` می‌زند (نه ریبوت، نه قطع تونل).

### ۲) `kcp` — تونل UDP+FEC موازی (A/B، بدون خرابکاری در سیستم فعلی)
kcptun یک تونل **UDP با FEC** می‌سازد که پکت‌های گم‌شده را بازسازی می‌کند، پس TCP داخلی یک مسیر تمیز می‌بیند. این حالت **افزودنی** است: rathole-server و nginx و ۴۴۳ دست‌نخورده می‌مانند؛ فقط یک مسیر ورودی دوم (UDP) ساخته می‌شود و نود می‌تواند بین دو مسیر سوییچ کند.

```bash
# روی ایران: مسیر UDP+FEC را روشن کن (پیش‌فرض پورت 443 = استتار شبیه QUIC، پروفایل balanced)
ratholectl kcp on                    # = kcp on 443 balanced
ratholectl kcp on 443 lossy          # loss زیاد روی مسیر → parity بیشتر
ratholectl kcp on 443 aggressive     # کم‌ترین لتنسی (mode fast3، پنجره بزرگ)
#  → کلید و دستور دقیق نود (با پروفایل) را چاپ می‌کند. پورت UDP را در فایروال باز کن:
#     ufw allow 443/udp     (یا Security Group ابری)   ← با nginx روی TCP/443 تداخل ندارد
ratholectl kcp status        # وضعیت + پروفایل + استتار
ratholectl kcp show          # دوباره چاپ دستور نود
ratholectl kcp off           # خاموش‌کردن مسیر UDP (برگشت کامل)

# روی نود: تونل را به مسیر kcp سوییچ کن (ip:port و کلید و پروفایل از خروجی بالا)
ratholenode kcp on <IRAN_IP>:443 <KEY> balanced
ratholenode kcp status
ratholenode kcp off          # برگشت فوری به websocket/443
```
سوییچ kcp **سرویس‌ها/توکن‌ها/path کاربران را تغییر نمی‌دهد** — کاربران لازم نیست ساب را آپدیت کنند؛ فقط مسیر حملِ همان تونل عوض می‌شود. اگر بهتر بود نگهش دار، اگر نه `kcp off` بزن.

> پروفایل‌ها (باید روی هر دو سر یکی باشند): `balanced` (10/3, fast2) ، `lossy` (10/5, fast2) ، `aggressive` (10/4, fast3, پنجره 4096).
> استتار: پورت **UDP/443** برای DPI شبیه QUIC/HTTP3 است. برای استتار قوی‌تر (udp2raw/obfs) به [`performance.md`](performance.md) نگاه کن.
> برای **سنجش قبل از سوییچ** هم اسکریپت‌های `kcptest-iran.sh` / `kcptest-node.sh` هستند که با iperf3 مسیر FEC را با مسیر مستقیم مقایسه می‌کنند.

#### kcp برای چند سرور ایران (multi-Iran) + مهاجرت
اگر نود به چند سرور ایران وصل است (یک `main` + چند `upstream`)، هر کدام می‌توانند **مستقل** kcp شوند. هر سرور ایران `ratholectl kcp on 443 <profile>` خودش را می‌زند؛ روی نود:
```bash
ratholenode migrate          # نقشه‌ی مهاجرت همه تونل‌ها + دستور دقیق هرکدام را چاپ می‌کند
# تونل اصلی:
ratholenode kcp on <IRAN1_IP>:443 <KEY1> balanced
# هر سرور ایران دوم/سوم (upstream) جداگانه:
ratholenode upstream kcp <id> on <IRAN2_IP>:443 <KEY2> balanced
ratholenode upstream kcp <id> status
ratholenode upstream kcp <id> off          # فقط همان upstream را برمی‌گرداند
```

#### مدیریت کامل upstreamها (چند سرور ایران)

```bash
ratholenode upstream add <id> <server:port> [hostname]   # تعریف upstream جدید
ratholenode upstream add-svc <id> <name> <token> <inbound>   # افزودن سرویس به upstream
ratholenode upstream rm-svc <id> <name>
ratholenode upstream rm <id>              # حذف کامل upstream + service
ratholenode upstream apply <id>           # بازتولید client.toml این upstream + hot-reload
ratholenode upstream restart <id>
ratholenode upstream status <id>
ratholenode upstream logs <id> [n]        # لاگ این upstream
ratholenode upstream ls                   # لیست همه upstreamها با transport جاری
ratholenode upstream ws <id>              # برگشت به transport=ws برای این upstream
ratholenode upstream plain <id> on <host:port> | off | status
ratholenode upstream noise <id> on <host:port> <pubkey> [pattern] | off | status
ratholenode upstream control-path <id> show | set <path> | clear   # مسیر مخفی کانال کنترل همین upstream
```
هر تونل kcp-client جداگانه با پورت لوکال متفاوت (main=29900 ، upstreamها از 29901) و سرویس systemd مستقل (`rathole-kcp-up-<id>`) دارد؛ پس روی هم اثر نمی‌گذارند و هرکدام مستقل قابل خاموش/روشن‌اند.

### ۲.۵) `noise` — تونل رمزنگاری‌شده بدون TLS/گواهی (جایگزین سبک TLS)
اگر می‌خواهی خودِ تونل **رمزنگاری‌شده** باشد ولی سربار و گواهیِ TLS را نداشته باشی، حالت `noise` از ترنسپورت داخلی **Noise** در rathole استفاده می‌کند (همان رمزنگاری WireGuard: X25519 + ChaChaPoly). سرور یک‌بار **جفت‌کلید** می‌سازد؛ نود فقط **کلید عمومی** را می‌گیرد (مثل مدل کلید kcp) — نیازی به cert نیست.

برخلاف `plain` (که هنوز در سطح rathole وب‌سوکت است و فقط TLS نگینکس را برمی‌دارد)، `noise` یک **ترنسپورت کاملاً متفاوت** است و از nginx رد نمی‌شود. برای همین روی یک **اینستنس دوم rathole** (`rathole-noise`) روی یک **پورت TCP عمومی جدا** اجرا می‌شود و انتخاب per-node است: هر نود یا روی noise می‌رود یا روی ws/443 می‌ماند (سرویس هر نود دقیقاً در یکی از `server.toml` یا `noise-server.toml` می‌رود — چون دو پروسه نمی‌توانند یک `bind_addr` را share کنند).

```bash
# روی ایران: اینستنس noise را روی یک پورت عمومی روشن کن (پیش‌فرض 2334؛ 443 و internal_port رد می‌شوند)
ratholectl noise on                  # = noise on 2334 ؛ جفت‌کلید را می‌سازد و دستور نود را چاپ می‌کند
#  → پورت TCP را در فایروال باز کن:   ufw allow 2334/tcp   (خودکار هم تلاش می‌شود)
ratholectl noise node <name> on      # این نود را به مسیر noise ببر (سرویسش به noise-server.toml می‌رود)
ratholectl noise node <name> off     # این نود را به ws/443 برگردان
ratholectl noise status              # روشن/خاموش + پورت + تعداد نودهای noise
ratholectl noise show                # دوباره چاپ دستور نود (کلید عمومی + پورت)
ratholectl noise off                 # خاموشیِ کامل: همه نودها به ws برمی‌گردند، سرویس/toml/unit حذف می‌شود

# روی نود: تونل را به مسیر noise سوییچ کن (ip:port و کلید عمومی از خروجی بالا)
ratholenode noise on <IRAN_IP>:2334 <PUBKEY> [<pattern>]
ratholenode noise status
ratholenode noise off                # برگشت فوری به websocket/443 (با TLS)
```
سوییچ noise هم **سرویس‌ها/توکن‌ها/path کاربران را تغییر نمی‌دهد** — فقط مسیر حملِ تونل رمزنگاری‌شده می‌شود.

> کلید عمومی قابل انتشار است؛ کلید خصوصی فقط روی ایران می‌ماند. پترن پیش‌فرض `Noise_NK_25519_ChaChaPoly_BLAKE2s` است (فقط سرور کلید استاتیک دارد). پورت noise **عمومی** است و باید در فایروال باز باشد؛ با ۴۴۳/game تداخل ندارد (رد می‌شود). در پنل وب هم دکمه‌های noise با **پرکردن خودکار کلید** از سرور ایران موجود است.

### ۲.۶) `backhaul` — هسته‌ی جدا با مالتی‌پلکس SMUX (پشت همان ۴۴۳)
rathole برای هر connection کاربر یک stream مجزا باز می‌کند و **mux ندارد**؛ روی لینک‌های شلوغ یا پرافت این گلوگاه می‌شود. حالت `backhaul` یک **هسته‌ی کاملاً جدا** (باینری Go از `Musixal/Backhaul`) را کنار rathole اجرا می‌کند که چند connection را با **SMUX** روی یک stream مالتی‌پلکس می‌کند.

برخلاف `noise` که روی یک پورت عمومی جدا می‌نشیند، backhaul **تک‌پورت/تک‌دامنه را حفظ می‌کند**: `backhaul-server` روی `127.0.0.1:<port>` (پیش‌فرض ۳۰۸۰) گوش می‌دهد و nginx مسیرهای `/channel` (کانال کنترلی) و `/tunnel` (دیتا) را روی همان ۴۴۳ به آن proxy می‌کند. این دو مسیر **در خود backhaul هاردکد شده‌اند** و قابل تغییر نیستند؛ چون کاربران به `/` (سایت فیک) و `/<node>` (دیتا) می‌روند، تداخلی پیش نمی‌آید.

```bash
# روی ایران: هسته را روشن کن (پورت داخلی است، نه عمومی)
ratholectl backhaul on                       # = backhaul on 3080 wsmux balanced
ratholectl backhaul on 3080 wsmux aggressive
ratholectl backhaul node <name> on           # این نود را به backhaul ببر
ratholectl backhaul node <name> off          # برگرداندنش به ws/443
ratholectl backhaul status                   # روشن/خاموش + transport دو طرف + نودها + وضعیت سرویس
ratholectl backhaul show                     # چاپ دوباره‌ی دستور آماده‌ی نود
ratholectl backhaul off                      # خاموشی کامل: همه نودها به ws برمی‌گردند، unit/toml حذف می‌شود

# روی نود: دقیقاً همان خطی که «show» بالا چاپ کرد
ratholenode backhaul on <DOMAIN> <TOKEN> wssmux balanced
ratholenode backhaul add-svc <name> <TOKEN> <inbound_port>
ratholenode backhaul rm-svc <name>
ratholenode backhaul ls
ratholenode backhaul status
ratholenode backhaul logs [n]
ratholenode backhaul off                     # خاموش‌کردن lane بک‌هال؛ lane رتهول مستقل می‌ماند
```

نکات کلیدی:

- **transport دو طرف عمداً یکی نیست.** چون TLS را فقط nginx ترمینیت می‌کند، سرور همیشه واریانت **بدون TLS** می‌گیرد (`ws`/`wsmux`) و کلاینت واریانت **TLS‌دار** (`wss`/`wssmux`) — دقیقاً همان قاعده‌ی rathole. هر دو سمت ورودی اشتباه را با پیام راهنما رد می‌کنند.
- **`tcpmux` پشتیبانی نمی‌شود**؛ TCP خام است و از nginx لایه ۷ رد نمی‌شود.
- **profile باید دو طرف یکی باشد** (`balanced`/`lossy`/`aggressive`). `mux_con` فقط سمت سرور و `connection_pool` فقط سمت کلاینت معنا دارد.
- **dual-core است.** روی ایران، هر مسیر فقط در یکی از `server.toml` یا mapping بک‌هال قرار می‌گیرد تا bind تکراری نشود. روی نود، `services.conf` برای rathole و `bh-services.conf` برای Backhaul است و هر دو client می‌توانند هم‌زمان سرویس‌های متفاوت را حمل کنند.
- **نگاشت پورت `"127.0.0.1:<port_ایران>=<inbound_port_نود>"`** است، یعنی همان پورتی که `map $uri` در nginx به آن اشاره می‌کند دست‌نخورده می‌ماند — **مسیر کاربران هرگز عوض نمی‌شود**. سرویس `<name>_api` هم اگر وجود داشته باشد اضافه می‌شود.
- توکن مشترک (`openssl rand -hex 20`) جای گواهی را می‌گیرد؛ **secret است** و فقط به نودهای backhaul داده می‌شود. در پنل وب دکمه‌های backhaul با **پرکردن خودکار دامنه و توکن** از سرور ایران موجود است.

### ۲.۷) `direct` — ورودیِ direct-IP با مسیریابیِ هدر (بدون TLS/احراز هویت)
یک **درگاهِ ورودیِ کاربریِ جدا** (نه یک حاملِ transport): کاربر **مستقیم به IP سرور ایران** روی یک پورت HTTP سادهٔ جداگانه (پیش‌فرض `8081`) وصل می‌شود و به‌جای `path`، از یک **هدرِ استتارشده** (پیش‌فرض `X-Cdn-Id`) برای انتخاب نود استفاده می‌کند — مقدارِ هدر = **نام نود**. هدرِ `Host` فقط یک **decoy** است (مثلاً `myket.ir`) و در مسیریابی نقشی ندارد. درخواستِ بدونِ هدرِ شناخته‌شده به **سایتِ فیک** می‌افتد (روی این پورت هیچ path-routing نیست). برخلاف path-routing که نامِ نود در URL دیده می‌شود (`/trk01/...`)، اینجا انتخابِ نود در یک هدر پنهان می‌شود — استتارِ بهتر برای دسترسی از راهِ IP خام.

```bash
# روی ایران: listenerِ direct-IP را روشن کن (پیش‌فرض port=8081, header=X-Cdn-Id؛ 443 و internal_port رد می‌شوند)
ratholectl direct on                       # = direct on --port 8081 --header X-Cdn-Id
ratholectl direct on --port 8081 --header X-Cdn-Id
#  → پورت TCP را در فایروال باز کن:   ufw allow 8081/tcp   (خودکار هم تلاش می‌شود)
ratholectl direct status                   # روشن/خاموش + پورت + نامِ هدر + listen-check + هدرِ هر نود
ratholectl direct show [name]              # چاپِ نمونه‌کانفیگِ کلاینت (Xray/V2Ray، WS بدون TLS)
ratholectl direct off                      # خاموشیِ کامل: maps و server block حذف می‌شوند
```

- **نمونهٔ کلاینت (Xray/V2Ray):** transport = WebSocket **بدون TLS**؛ `address:port` = `<IRAN_IP>:8081`؛ `ws Host` = یک domainِ decoy؛ هدرِ اضافه = `<direct_header>: <node_name>`؛ `ws path` = همان path معمولِ نود.
- **اشتراکِ پورت با plain:** اگر `direct_port == plain_port` باشد، فقط **یک** server block روی آن پورت ساخته می‌شود؛ هدرِ شناخته‌شده برنده است و هدرِ خالی/ناشناس به path-routing (`$backend_port`) می‌افتد.
- **نودهای SNI مستثنا هستند** (روی ۴۴۳ passthroughِ لایه ۴ هستند و پورتِ لوکالِ لایه ۷ برای HTTP ساده ندارند).
- در پنل وب هم دکمهٔ direct-IP با فرمِ port/header موجود است.

### ۲.۸) `proxy` — ریورس‌پروکسی غیرتونلی روی همان ۴۴۳

گاهی خودت یک تونل یا سرویسِ **کاملاً مستقل** داری که rathole مدیریتش نمی‌کند (مثلاً یک Xray/V2Ray یا وب‌سرویس دیگر روی همین یا یک میزبان دیگر) و می‌خواهی از همان **دامنه/گواهی/پورت ۴۴۳** سرو شود. `ratholectl proxy` یک مسیر `/<name>/` می‌سازد که به یک upstream دلخواه proxy می‌شود — **بدون عبور از rathole**:

```bash
# روی ایران:
ratholectl proxy add mysvc http://127.0.0.1:9000    # /<mysvc>/ → http://127.0.0.1:9000/
ratholectl proxy add ext https://10.0.0.5:8443      # upstream می‌تواند https یا میزبان دیگر هم باشد
ratholectl proxy ls                                 # لیست + URL کاربر هر مسیر
ratholectl proxy rm mysvc
```

نکات کلیدی:

- **upstream فقط `http(s)://host:port` است** — بدون مسیر، بدون query، بدون هیچ متاکاراکتری؛ با regex سخت اعتبارسنجی می‌شود چون مستقیم به کانفیگ nginx می‌رود.
- **فضای‌نام مشترک با نودها:** هر دو در `map $uri` می‌نشینند؛ پس `proxy add` با نام یک نودِ موجود رد می‌شود و `ratholectl add` هم با نام یک proxyِ موجود رد می‌شود. نام‌های رزروی nginx (`sub`, `hub`, `channel`, `tunnel`) هم پذیرفته نمی‌شوند.
- **امنیت:** این قابلیت به اپراتور اجازه می‌دهد nginx را به میزبان دلخواه اشاره دهد؛ upstream **اعتمادشده** فرض می‌شود (اپراتور خودش انتخابش می‌کند). از هاب هم با اکشن‌های `proxy_add`/`proxy_rm`/`proxy_ls` (با همان regexها و argv جدا) در دسترس است.
- ساختار state: `.proxies[]` با `{name, upstream}`؛ هر تغییر مثل بقیه‌ی دستورها کانفیگ را بازتولید و hot-reload می‌کند.

### ۲.۹) `frp` — هسته‌ی ریورس تونل مستقل fatedier/frp

یک **هسته‌ی جدا و بالغ (`fatedier/frp`)** کنار rathole و backhaul. مناسب برای شرایطی که نیاز به مالتی‌پلکسینگ پیشرفته TCP/QUIC/KCP/WebSocket با قابلیت‌های احراز هویت توکن مشترک و نگاشت مستقیم پورت‌های لوکال است:

```bash
# روی ایران: هسته frps را روشن کن
ratholectl frp on [port] [token] [transport]     # پیش‌فرض: port=7000، token خودکار، transport=tcp
# میان‌بر: اگر جای token نام یک transport بدهی، خودش همان را transport می‌گیرد → ratholectl frp on 7000 quic
ratholectl frp show [name]                       # نمایش دستور آماده کلاینت نود
ratholectl frp node <name> on|off                # این نود را به مسیر FRP ببر / برگردان
ratholectl frp ready <name>                      # صبر تا proxy نود روی 127.0.0.1:<port> ثبت شود
ratholectl frp status                            # وضعیت پروسه frps و پورت‌ها
ratholectl frp off                               # خاموش‌کردن کامل سرویس frps

# روی نود خارج: کلاینت frpc را روشن کن
ratholenode frp on <IRAN_IP:PORT> <TOKEN> [transport] [remote_port]   # transport: tcp, kcp, quic, websocket
# remote_port = پورت سمت ایران برای سرویس این نود (از خروجی `frp show` روی پنل)
ratholenode frp status
ratholenode frp off
```

### ۲.۱۰) `gre` — تونل شبکه لایه ۳ کرنل لینوکس (ip tunnel)

تونل **شبکه لایه ۳ نقطه به نقطه (Generic Routing Encapsulation)** مبتنی بر کرنل لینوکس، مناسب برای شبکه‌سازی مستقیم IP بین سرور ایران و سرور خارج بدون نیاز به هیچ باینری یا پراکسی واسط:

```bash
# روی ایران: اینترفیس gre1 را با ساب‌نت /30 بساز
ratholectl gre on <NODE_REMOTE_IP> [tunnel_ip] [gre_name]   # پیش‌فرض آی‌پی تونل: 10.10.10.1/30
ratholectl gre status [gre_name]
ratholectl gre off [gre_name]

# روی نود خارج: انتهای تونل gre را متصل کن
ratholenode gre on <IRAN_REMOTE_IP> [tunnel_ip] [gre_name]  # پیش‌فرض آی‌پی تونل: 10.10.10.2/30
ratholenode gre status [gre_name]
ratholenode gre probe <PEER_IP> [gre_name]   # سنجش دسترسی peer روی اینترفیس GRE (ping -I)
ratholenode gre off [gre_name]
```

- **بهینه‌سازی شبکه:** تنظیم خودکار `MTU 1476` و اعمال قانون `TCPMSS clamping` در iptables جهت جلوگیری از تکه‌تکه شدن (fragmentation) بسته‌های TCP بر بستر اینترنت ایران.

### ۲.۱۱) `frp + gre` — پروتکل ترکیبی لایه ۳ با حامل استریم ضد اختلال

ترکیب **FRP (حامل استریم)** با **GRE (لایه ۳)**:
در شرایطی که پکت‌های خام GRE (پروتکل ۴۷) توسط فیلترینگ دچار اختلال، دراپ یا تراتلینگ می‌شوند، FRP با ترانسپورت‌های **QUIC** (بر پایه UDP مالتی‌پلکس)، **KCP** (تصحیح خطا)، **WebSocket** یا **TCP** استریم تونل را پنهان‌سازی کرده و همزمان اینترفیس مجازی GRE با رنج آی‌پی `10.10.10.1/30` و `10.10.10.2/30` امکان اتصال مستقیم لایه ۳ بین ایران و خارج را فراهم می‌آورد. این حالت ترکیبی از CLI ساخته می‌شود: GRE را روی هر دو سمت با `gre on` بساز و FRP را با ترانسپورت `quic`/`kcp`/`websocket` روی همان مسیر اجرا کن. در هاب هم از دکمهٔ «حامل و پروتکل» هر سرویس، گزینهٔ `frp+gre` («ترکیبی FRP + GRE») قابل انتخاب است (هاب اول GRE دو طرف را می‌سازد و با `gre_probe` چک می‌کند، بعد FRP را روی IP مجازی GRE می‌برد). توجه: پس از اعمال، رکورد ایران روی lane `FRP` ثبت می‌شود و برچسب گزارش‌شدهٔ سرویس `FRP / <transport>` است؛ سالم بودن خودِ GRE را با `gre probe`/«تست سلامت» جداگانه تأیید کن.

### ۳) توصیه‌های کلاینت/نود
- روی کانفیگ کلاینت‌ها برای استریم/لتنسی **`mux=off`** بگذار (mux برای ریلز ضرر دارد).
- اگر `kcp` هم لگ را حل نکرد، احتمالاً **IP نود** کثیف/throttle است؛ نود تمیزتر را امتحان کن.

## نکات کلیدی فنی

- کانال کنترلی rathole به‌طور پیش‌فرض روی مسیر `/` با هدر WebSocket Upgrade وصل می‌شود و nginx ریشه را با `$http_upgrade` بین «سایت فیک» و «کانال کنترل» تفکیک می‌کند. با coreهای جدید می‌توان همین مسیر را به `/_rh/<hex32>` برد (`ratholectl control-path rotate`)؛ در این حالت nginx یک `location` دقیق برای همان مسیر می‌سازد و `/` هم به‌عنوان fallback برای نودهای قدیمی کار می‌کند.
- TLS را فقط **nginx** ترمینیت می‌کند؛ ترنسپورت rathole روی سرور `websocket` با `tls=false` و روی کلاینت `websocket` با `tls=true` است. (استثنا: حالت `noise` یک اینستنس دوم rathole با ترنسپورت `noise` روی پورت عمومی است که خودش رمزنگاری می‌کند و از nginx رد نمی‌شود.)
- هر نود یک سرویس **دیتا** دارد؛ و اگر `--api-port` بدهی یک سرویس **مدیریت** (`_api`) هم برای ارتباط پنل↔نود ساخته می‌شود که روی `127.0.0.1` ظاهر می‌گردد.
- **path در سه جا باید یکی باشد:** کانفیگ کاربر = `map` در nginx = اینباند Xray روی نود. نام نود = همان path.

## هاب (پنل مرکزی، وب)

هاب یک پنل وب است که چند سرور ایران و نود را از یک نقطه مدیریت می‌کند. روی همان سرور ایران نصب می‌شود، پشت همان دامنه/گواهی/۴۴۳ زیر `/<hub-path>/` (پیش‌فرض `/hub/`) سرو می‌شود، و خودِ سرویس فقط روی `127.0.0.1:8088` (پیش‌فرض) گوش می‌دهد:

```bash
ratholectl hub on [port]        # بار اول هاب را نصب و سرویس/کانفیگ/رمز را می‌سازد؛ دفعات بعد فقط listen_port را همگام می‌کند
ratholectl hub status           # آدرس https پشت nginx، پورت داخلی و وضعیت ratholehub
ratholectl hub off              # location پنل را از nginx برمی‌دارد (سرویس روی 127.0.0.1 روشن می‌ماند)
ratholectl hub auto-add         # همین سرور ایران را خودکار در inventory هاب ثبت می‌کند
ratholectl set hub-path <seg>   # تغییر مسیر پنل (پیش‌فرض: hub)
```

> نصب دستی/مستقل هم ممکن است: `sudo bash ratholehub/install-hub.sh`. رمز اولیه و توکن API را از «تنظیمات» عوض کن؛ تا وقتی عوض نشده‌اند هشدار «رمز/توکن پیش‌فرض امن نیست» نشان داده می‌شود.

### صفحه‌ها و مسیرها

| مسیر | کار |
|------|-----|
| `#/dashboard` | پیش‌فرض؛ کارت/لیست سرورها، وضعیت و نسخهٔ هر سرور |
| `#/server/<name>` | صفحهٔ یک سرور (ایران یا نود): سرویس‌ها، حامل‌ها، ingress، دیاگ، upstream |
| `#/routing` | نقشهٔ توپولوژی **فقط-خواندنی** (کنسول/گراف/جدول) — تغییر مسیر از اینجا انجام نمی‌شود |
| `#/audit` | ۱۰۰ فعالیت اخیر (زمان/کاربر/عملیات) |
| `#/settings` | رمز عبور، توکن API، listen، پروکسی هاب |

> آدرس‌های قدیمی/ناشناس بی‌صدا به `#/dashboard` می‌افتند.

### مدیریت سرویس‌ها (دکمه‌های هر ردیف)

روی **هر دو** صفحهٔ سرور ایران و نود، هر ردیف سرویس همین پنج دکمه را دارد:

| دکمه | کار |
|------|-----|
| **«حامل و پروتکل»** | تغییر حامل همان سرویس (`ws`/`kcp`/`plain`/`noise`/`backhaul`/`frp`/`gre`/`frp_gre`) با حفظ پورت اینباند و تنظیم خودکار هر دو سمت |
| **«تست سلامت»** | اجرای `doctor` روی سرور ایران و نمایش خروجی |
| **«ساخت کانفیگ VLESS»** | ساخت و کپی لینک `vless://<uuid>@<host>:443?type=ws&security=tls&path=/<name>&sni=...` (UUID واقعی کاربر Xray + دامنه/IP عمومی) |
| **«مدیریت سمت مقابل»** | پرش به صفحهٔ سرور طرف مقابل همان سرویس |
| **«حذف از دو سمت»** | حذف سرویس از ایران و نود با هم؛ اگر وضعیت سمت مقابل در دسترس/تازه نباشد عمل نمی‌کند |

> سرویس‌های SNI/گیم از «حامل و پروتکل» و «ساخت کانفیگ VLESS» مدیریت نمی‌شوند و پیام راهنما («از بخش سرویس‌های گیمینگ مدیریت کنید») نشان داده می‌شود.

### برچسب حامل و پروتکل

هر سرویس برچسبی از **پروتکل گزارش‌شده از سرور** نشان می‌دهد: `FRP / QUIC`، `Backhaul / WSMUX`، `KCP / UDP · balanced`، `Noise / TCP`، `WebSocket / TLS`، `WebSocket / TCP`، `GRE / WebSocket`، `SNI / TLS`. علامت `?` یعنی پروتکل از سرور گزارش نشده است — برچسب به‌تنهایی دلیل سالم بودن مسیر نیست؛ «تست سلامت» این را روشن می‌کند. حالت هیبرید `frp+gre` روی lane `FRP` ثبت می‌شود و برچسبش `FRP / <transport>` است.

### نکات دیگر پنل

- هر سرور `transport: ssh|api` دارد و با نشان **⚡ REST API** یا **🔑 SSH** مشخص می‌شود (بخش «آژنت REST» پایین‌تر).
- دکمهٔ **«آپدیت همه»** سرورها را یکی‌یکی و ترتیبی آپدیت می‌کند؛ نسخهٔ هر سرور به‌صورت badge سبز (به‌روز) یا قرمز (`vX → vY`، قدیمی) روی کارت/صفحه‌اش دیده می‌شود.
- صفحهٔ ایران: نودها/سرویس‌ها، سرویس‌های game/SNI، حامل‌ها (backhaul/kcp/plain/noise/frp/gre)، ingress (direct-IP، fakeweb)، دامنه‌ها/TLS، باکس هاب، ابزارهای دیاگ و upstream.
- صفحهٔ نود: انتخاب حامل، ری‌استارت، watchdog، adaptive، جدول یکپارچهٔ سرویس‌ها (لِین rathole + لِین Backhaul با برچسب lane)، upstreamها (هرکدام حامل خودش) و دیاگ.

## آژنت REST (مدیریت سرور بدون SSH)

یک دِیمون کوچک پایتون (فقط stdlib) روی سرور ایران یا نود، HTTP(S) با توکن ارائه می‌دهد و هاب به‌جای SSH از همان استفاده می‌کند (رکورد سرور: `transport: "api"`).

### نصب و فرمان‌ها

روی سرورِ نصب‌شده (پنل/نود) فایل‌های آژنت از قبل هستند و `/usr/local/bin/install-agent.sh` لینک شده است؛ نیازی به دانلود نیست:

```bash
sudo install-agent.sh --role iran            # روی پنل (پورت پیش‌فرض 8089)
sudo install-agent.sh --role node --port 8089 --token <T>
```

یا از خود CLIها (همان کار + چاپ تنظیمات اتصال؛ نقش را خودِ CLI تعیین می‌کند):

```bash
sudo ratholectl agent on [port] [token]     # ایران؛ پیش‌فرض 8089
sudo ratholenode agent on [port] [token]    # نود
sudo ratholectl agent off | status | token | show | restart
```

- توکن اگر داده نشود از `/etc/rathole-agent/token` خوانده یا خودکار ساخته می‌شود (`chmod 600`).
- واحد systemd: `rathole-agent.service` با `Restart=always`.
- `update.sh` فایل‌های آژنت را هم به‌روز می‌کند، یونیت را ری‌استارت می‌کند و توکن `/etc/rathole-agent/token` را حفظ می‌کند؛ uninstallerها یونیت و `/etc/rathole-agent` را پاک می‌کنند.

### API

```bash
# سلامت (بدون احراز):
curl http://<IP>:8089/api/ping
# → {"ok": true, "role": "node", "version": "1.0.0", "hostname": "..."}

# اجرای دستور (argv؛ Bearer token):
curl -H "Authorization: Bearer <TOKEN>" -H 'Content-Type: application/json' \
  -d '{"cmd": ["ratholectl","status","--json"], "timeout": 120}' \
  http://<IP>:8089/api/exec
# → {"ok": true, "rc": 0, "out": "...", "err": ""}
```

- احراز: `Authorization: Bearer <token>` با مقایسهٔ constant-time؛ 401 برای هدر نبود/اسکیم اشتباه و 403 برای توکن غلط.
- `/api/exec` فقط argv از باینری‌های مجاز را اجرا می‌کند: `ratholectl`، `ratholenode`، `bash`، `python3`، `systemctl`، `journalctl`، `curl`، `jq`، `cat`، `tail`، `ls`. بدنه ۱ بایت تا ۱ مگابایت و `timeout` بین ۱ تا ۳۶۰۰ ثانیه است.
- **HTTPS:** با `--tls-cert`/`--tls-key` (یا env `RATHOLE_AGENT_TLS_CERT`/`RATHOLE_AGENT_TLS_KEY`)، یا کافی است `/etc/rathole-agent/cert.pem` و `key.pem` را بگذاری تا خودکار HTTPS شود. برای گواهی self-signed، هاب باید verify را رد کند: در رکورد همان سرور در `/etc/ratholehub/inventory.json` مقدار `insecure_ssl: true` را بگذار، یا هاب را با `RATHOLE_AGENT_INSECURE_SSL=1` اجرا کن.
- **اتصال از هاب:** Add Server → Connection: «⚡ اتصال Agent REST API (مستقیم)» → API URL (`http://IP:8089`) + Token. در لیست سرورها با نشان ⚡ REST API دیده می‌شود. پورت باید از هاب قابل دسترس باشد (فایروال)؛ روی اینترنت، HTTPS با گواهی معتبر + توکن قوی توصیه می‌شود.

## شروع سریع

> می‌خواهی **دستی و گام‌به‌گام** نصب کنی (پنل ایران + کانفیگ پاسارگارد + نودها + هاب)؟ راهنمای کامل: [`install-manual.fa.md`](install-manual.fa.md).

### نصب تک‌کامانده از گیت‌هاب (curl | sudo bash)

ساده‌ترین راه؛ آخرین بسته‌ی release را از گیت‌هاب می‌گیرد و نصاب را اجرا می‌کند. پیش‌فرض روی `l8PYGIT/RatholeEngine` است — برای fork خودت متغیر `RATHOLE_GH` را ست کن:

```bash
# کاملاً تعاملی (حالت پنل/نود و اطلاعات را می‌پرسد)
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash

# سرور ایران (پنل) غیرتعاملی:
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --panel \
  --domain panel.example.ir \
  --fullchain /root/cert/panel.example.ir/fullchain.pem \
  --key       /root/cert/panel.example.ir/privkey.pem

# نود خارج غیرتعاملی:
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \
  --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087

# آپدیت کامل (تشخیص خودکار پنل/نود/هاب، با snapshot + رولبک خودکار):
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --update
```

> `install.sh` فایل‌های `rathole-manager.zip` و `bootstrap.sh` را از آخرین GitHub Release (که workflowِ release می‌سازد) دانلود می‌کند و بعد به `bootstrap.sh` تحویل می‌دهد. برای تغییر مخزن: `RATHOLE_GH="you/repo"`.
>
> **نصب یک نسخه‌ی خاص:** با فلگ `--release` (اگر بدون آرگومان اجرا کنی، خودش می‌پرسد؛ Enter = آخرین نسخه):
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --release v2.0.2 --panel --domain ... --fullchain ... --key ...
> ```
>
> `--beta` آخرین pre-release و `--stable` آخرین نسخه‌ی پایدار را می‌گیرد. از روی سرورِ نصب‌شده: `ratholectl update v2.0.2` یا `ratholenode update v2.0.2`.
> دقت کن `RATHOLE_RELEASE=... curl ... | sudo bash` کار **نمی‌کند** (آن متغیر به `curl` می‌چسبد و `sudo` هم پاکش می‌کند) — از فلگ استفاده کن.
>
> **در ایران (فیلترینگ گیت‌هاب):** اگر دانلود مستقیم گیت‌هاب کار نکرد، بسته را روی سرور خارج بگیر و از روش «بسته‌ی محلی» زیر (`bootstrap.sh --local`) استفاده کن.

### آپدیت و رولبک

`update.sh` قبل از هر تغییر یک **snapshot کامل** (CLI + کانفیگ‌ها + یونیت‌های systemd) در `/var/backups/rathole-manager/pre-update-<ts>/` (شامل `manifest.txt` و `backup.tar.gz`) می‌گیرد، بعد از آپدیت **health-check** می‌زند (سرویس بالا آمد؟ `nginx -t` سالم؟) و اگر خراب بود **خودکار به snapshot برمی‌گردد**.

> **ساده‌ترین راه از خودِ سرور:** `sudo ratholectl update` (روی ایران) یا `sudo ratholenode update` (روی نود) — `install.sh` آخرین Release را از GitHub (با mirrorهای ghproxy برای دور زدن فیلترینگ) می‌گیرد و همین `update.sh` را با snapshot + rollback اجرا می‌کند. در **هاب** هم دکمه‌ی «آپدیت» هر سرور دقیقاً همین کار را از راه دور انجام می‌دهد (دیگر به bundle محلی هاب وابسته نیست).

> **آپدیت همه از هاب:** در داشبورد هاب دکمهٔ **«آپدیت همه»** همهٔ سرورها (ایران + نود) را **یکی‌یکی و ترتیبی** آپدیت می‌کند و یک **progress bar** + وضعیت زندهٔ هر سرور (در صف / در حال آپدیت / ✓ / ✗ + نسخهٔ جدید) نشان می‌دهد. نسخهٔ نصب‌شده روی هر سرور به‌صورت **badge** روی کارت/صفحهٔ سرور دیده می‌شود: **سبز** = به‌روز، **قرمز** = قدیمی (`vX → vY`، نیاز به آپدیت). این نسخه از دستور `ratholectl/ratholenode version` خوانده و با آخرین نسخه (`MANAGER_VERSION` در `common.sh`) مقایسه می‌شود. (نکته: خودِ سروری که هاب رویش است هم در «آپدیت همه» هست؛ هنگام ری‌استارت هاب ممکن است progress همان یکی نیمه بماند، بقیه کامل می‌شوند.)

```bash
sudo ratholectl update                  # روی ایران: آپدیت کامل از GitHub (آخرین Release)
sudo ratholenode update                 # روی نود:  آپدیت کامل از GitHub (آخرین Release)
sudo bash update.sh                     # آپدیت با snapshot + health-check + رولبک خودکار
sudo bash update.sh --list-backups      # لیست snapshotها
sudo bash update.sh --rollback          # بازگشت به آخرین snapshot
sudo bash update.sh --rollback 20260713-2210   # بازگشت به snapshot مشخص
sudo bash update.sh --no-rollback       # آپدیت بدون بازگشت خودکار (فقط snapshot بگیر)
```

آخرین ۷ snapshot نگه داشته می‌شوند (با `RATHOLE_BACKUP_RETENTION` قابل تغییر). رولبک از هر مسیر دیگری هم قابل‌فراخوانی است: `sudo bash bootstrap.sh --rollback` یا `--list-backups`.

#### مخزن خصوصی (GitHub Private)

اگر کد/ریلیزها در مخزن خصوصی است، دانلود بدون توکن کار نمی‌کند و mirrorهای عمومی ghproxy هم کنار گذاشته می‌شوند:

```bash
# ۰) توکن با دسترسی Contents:read را در همین شل بگذار (فقط برای همین نشست):
export RATHOLE_GH_TOKEN=github_pat_xxx

# ۱) خودِ install.sh را از مخزن خصوصی با هدر احراز بگیر:
curl -fsSL -H "Authorization: Bearer $RATHOLE_GH_TOKEN" \
  "https://raw.githubusercontent.com/OWNER/REPO/main/install.sh" -o /tmp/install.sh

# ۲) slug مخزن را با env و توکن را با --token بده تا bootstrap/بسته هم از همان مخزن خصوصی دانلود شوند:
sudo env RATHOLE_GH="OWNER/REPO" bash /tmp/install.sh \
  --token "$RATHOLE_GH_TOKEN" --panel --domain ...
```

- `install.sh` فلگ `--token`/`-t` را می‌شناسد؛ توکن از env هم خوانده می‌شود: `RATHOLE_GH_TOKEN` (یا `GH_TOKEN`/`GITHUB_TOKEN`). فایل‌های raw با هدر `Authorization: Bearer` دانلود می‌شوند و در صورت نیاز از آرشیو API گیت‌هاب استفاده می‌شود؛ **برای مخزن خصوصی mirrorهای عمومی حذف می‌شوند**. slug مخزن از `RATHOLE_GH` خوانده می‌شود (پیش‌فرض `l8PYGIT/RatholeEngine`) و توکن به‌صورت `RATHOLE_GH_TOKEN` به `bootstrap.sh` تحویل داده می‌شود.
- **روی سرور نصب‌شده:** `sudo env RATHOLE_GH="OWNER/REPO" bash tools/update-private.sh` — آخرین release asset (یا سورس `main` با `RATHOLE_RELEASE=main`) را می‌گیرد و `bootstrap.sh --local --update` را اجرا می‌کند (همان snapshot + health-check + rollback). توکن را مخفی می‌پرسد یا از `RATHOLE_GH_TOKEN` می‌خواند و در پایان از محیط unset می‌کند. نسخه با `RATHOLE_RELEASE` تعیین می‌شود. (این فایل داخل بستهٔ نصبی نیست؛ از checkout/مخزن برش دار و روی سرور اجرا کن.)
- `ratholectl update` / `ratholenode update` از مسیر mirrorهای **عمومی** گیت‌هاب استفاده می‌کنند؛ برای مخزن خصوصی به‌جای آن‌ها `tools/update-private.sh` را روی همان سرور اجرا کن.

### نصب تک‌خطی با bootstrap (دانلود + باز کردن + نصب)

`bootstrap.sh` بیرون از بسته قرار دارد. اگر بسته (`rathole-manager.zip` یا `.tar.gz`) **کنار اسکریپت یا در مسیر جاری باشد، دانلود نمی‌کند** و از همان استفاده می‌کند. اگر اطلاعات کافی ندهی، **به‌صورت تعاملی می‌پرسد**.

```bash
# کاملاً تعاملی: حالت (پنل/نود) و اطلاعات را می‌پرسد، و اگر زیپ کنارش باشد دانلود نمی‌کند
sudo bash bootstrap.sh

# با بسته‌ی محلی صریح (بدون دانلود):
sudo bash bootstrap.sh --local ./rathole-manager.zip

# سرور ایران (پنل) غیرتعاملی:
sudo bash bootstrap.sh --url https://YOUR_LINK/rathole-manager.zip --panel \
  --domain panel.example.ir \
  --fullchain /root/cert/panel.example.ir/fullchain.pem \
  --key       /root/cert/panel.example.ir/privkey.pem

# نود خارج غیرتعاملی:
sudo bash bootstrap.sh --url https://YOUR_LINK/rathole-manager.zip --node -- \
  --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087

# فقط آماده‌سازی و باز کردن (بدون اجرای نصاب):
sudo bash bootstrap.sh --local ./rathole-manager.zip --no-run
```

`bootstrap.sh` خودش:
- پکیج‌منیجر را تشخیص می‌دهد (apt/dnf/yum/pacman/apk) و `curl unzip tar ca-certificates` را نصب می‌کند
- **منبع بسته را تعیین می‌کند:** `--local` → سپس `--url` (اگر file:// یا مسیر محلی باشد کپی، وگرنه دانلود) → سپس **جستجوی خودکار بسته‌ی محلی** (بدون دانلود) → در نهایت پرسش تعاملی URL/مسیر
- بسته را (zip یا tar.gz) باز می‌کند، در `/opt/rathole-manager` می‌گذارد، خط‌پایان‌ها را LF و اسکریپت‌ها را قابل‌اجرا می‌کند
- اگر حالت مشخص نباشد، **منوی انتخاب** (پنل / نود / آپدیت / فقط‌آماده‌سازی / رولبک / لیست بکاپ / **حذف کامل**) را نشان می‌دهد؛ برای نود اطلاعات (server/name/token/inbound/api) را می‌پرسد؛ برای پنل، `install-panel.sh` خودش به‌صورت تعاملی می‌پرسد

> فلگ‌ها: `--url`, `--local`, `--dir`, `--panel`, `--node`, `--update`, `--rollback`, `--list-backups`, `--uninstall`/`--remove`, `--purge`, `--no-run`, `--yes`. هر آرگومانی بعد از `--` (یا ناشناخته) به نصاب پاس داده می‌شود.

### نصب دستی (اگر فایل‌ها را از قبل داری)

روی سرور ایران، فقط همین یک اسکریپت همه‌چیز را خودکار انجام می‌دهد:

```bash
sudo bash install-panel.sh
```

> **نصب مجدد / ناقص:** اگر نصب قبلی (کامل یا نیمه‌کاره) روی سرور باشد، `install-panel.sh` وضعیت هر جزء (باینری/`ratholectl`/`common.sh`/systemd/state/`server.toml`/nginx) را با ✓/✗ نشان می‌دهد و بین دو حالت انتخاب می‌دهد:
> - **تکمیل (resume)** — فقط اجزای گم‌شده کامل می‌شوند و state/کانفیگ حفظ می‌شود (پیش‌فرض؛ فلگ `--repair`).
> - **از‌نو (fresh)** — کانفیگ/state با بکاپ در `/var/backups/rathole-manager/fresh-reset-*` پاک و از ابتدا ساخته می‌شود (باینری و گواهی دست‌نخورده؛ فلگ `--fresh`).
>
> زیر `curl … | bash` (بدون ترمینال) به‌صورت خودکار حالت امنِ **تکمیل** انتخاب می‌شود.

### حالت فلگ‌محور (وقتی دامنه/گواهی/پورت‌هایت فرق دارد و گواهی از قبل داری)

می‌توانی همه مقادیر را مستقیم بدهی تا بدون پرسش و **بدون certbot** اجرا شود.
مهم‌تر از همه: با `--nginx-conf` می‌توانی **فایل کانفیگ nginx فعلی‌ات را مستقیماً ریپلیس کنی** (از فایل قبلی یک `.rathole-orig.bak` گرفته می‌شود):

```bash
sudo bash install-panel.sh \
  --domain example.ir \
  --fullchain /root/cert/example.ir/fullchain.pem \
  --key       /root/cert/example.ir/privkey.pem \
  --nginx-conf /etc/nginx/sites-available/example.ir.conf \
  --fake-port 8080 --sub-port 2096 --control-port 2333
```

فلگ‌های `ratholectl init`:

| فلگ | پیش‌فرض | توضیح |
|-----|---------|-------|
| `--domain` | (الزامی) | دامنه |
| `--fullchain` | `/root/cert/<domain>/fullchain.pem` | گواهی موجود |
| `--key` | `/root/cert/<domain>/privkey.pem` | کلید موجود |
| `--nginx-conf` | `/etc/nginx/conf.d/rathole.conf` | فایلی که تولید/ریپلیس می‌شود |
| `--fake-port` | `8080` | سایت فیک/پنل پاسارگارد |
| `--sub-port` | `2096` | ساب‌اسکریپشن |
| `--control-port` | `2333` | کنترل لوکال rathole |
| `--data-start` | `1001` | شروع پورت دیتای نودها |
| `--api-start` | `7001` | شروع پورت مدیریت نودها |
| `--certbot` | (خاموش) | فقط اگر بدهی، گواهی با certbot گرفته می‌شود |

> گواهی **هیچ‌وقت تحمیل نمی‌شود**؛ اگر مسیر گواهی موجود باشد همان استفاده می‌شود. certbot فقط با `--certbot` یا در حالت تعاملی با تأیید تو اجرا می‌شود.

> هر چیزی که در فایل nginx هدف باشد ریپلیس می‌شود، ولی سایت فیک/پنل پاسارگاردت باید روی پورت لوکال (`--fake-port`) سرو شود؛ کانفیگ تولیدی default را به همان پورت می‌فرستد.

سپس افزودن نود:

```bash
sudo ratholectl add trk01 2087        # نام=trk01 ، پورت اینباند Xray روی نود=2087
sudo ratholectl add usa01 2087 --api-port 62050   # با کانال مدیریت پنل↔نود
```

دستور بالا توکن و «دستور نصب نود» چاپ می‌کند. آن را روی نود خارج اجرا کن:

```bash
sudo bash install-node.sh --server example.ir:443 --name trk01 \
     --token <TOKEN> --inbound-port 2087
```

بررسی سلامت کل سیستم در هر زمان:

```bash
sudo ratholectl doctor
```

سپس روی نود، در پنل/Xray یک اینباند **VLESS + WS (یا HTTPUpgrade)** با `path=/trk01`، `listen=127.0.0.1`، `port=2087`، **TLS خاموش** بساز.
کانفیگ کاربر: `address=example.ir`، `port=443`، `ws`، `path=/trk01`، `TLS=on`.

جزئیات کامل و عیب‌یابی در `rathole-multilocation-pasargad.md`.

## حذف (Uninstall)

**ساده‌ترین راه (هر سروری) — یک دستور، تشخیص خودکار نقش:**

```bash
sudo bash bootstrap.sh --uninstall        # پنل/نود/هاب نصب‌شده را تشخیص و با تأیید حذف می‌کند
sudo bash bootstrap.sh --purge --yes       # + باینری rathole و کانفیگ هاب، بدون پرسش
```

`bootstrap.sh` نقش‌های نصب‌شده روی سرور را تشخیص می‌دهد و uninstaller هر کدام را اجرا می‌کند (هاب مستقیم، چون اسکریپت جدا ندارد). همین گزینه در **منوی تعاملی** هم هست (گزینهٔ ۷: حذف کامل).

**یا مستقیم، اسکریپت هر نقش:**

روی سرور ایران:

```bash
sudo bash uninstall-panel.sh          # سرویس/کانفیگ/state را حذف و بکاپ nginx را ری‌استور می‌کند
sudo bash uninstall-panel.sh --purge --yes   # باینری rathole هم حذف، بدون پرسش
```

روی هر نود خارج:

```bash
sudo bash uninstall-node.sh           # کلاینت rathole را حذف می‌کند (به nginx/Xray نود دست نمی‌زند)
sudo bash uninstall-node.sh --purge --yes
```

> `uninstall-panel.sh` اگر فایل `*.rathole-orig.bak` وجود داشته باشد، کانفیگ nginx اصلی‌ات را **برمی‌گرداند**. بکاپ‌های پوشه‌ای تداخل (`/etc/nginx/rathole-backup-*`) دست‌نخورده می‌مانند تا در صورت نیاز دستی برگردانی. `common.sh` مشترک فقط وقتی حذف می‌شود که نقش دیگری (نود/هاب) روی همان سرور نباشد. گواهی Let's Encrypt هم عمداً حذف نمی‌شود.

> اگر آژنت REST (`rathole-agent`) نصب باشد، `uninstall-panel.sh` / `uninstall-node.sh` یونیت آن و پوشهٔ `/etc/rathole-agent` را هم پاک می‌کنند.


## حمایت مالی

اگر RatholeEngine برایتان مفید بوده، با یکی از روش‌های زیر از توسعه‌ی مستمر آن حمایت کنید:

| شبکه | آدرس |
|------|------|
| **USDT (BEP-20 / BSC)** | `0x2364898407e8A42DA554B909989cd9B28eE61314` |
| **TON** | `UQCondoXRwQNt0fQvvmYGa_Fn39D9szjQH4eBqIcUd5r1yfH` |
| **TRX (Tron)** | `TRhnkJFpj9uxA2aqUxapJAFhkzNPbfxKwp` |

</div>
