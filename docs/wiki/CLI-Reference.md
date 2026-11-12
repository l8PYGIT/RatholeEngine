# مرجع کامل دستورات CLI

**نسخه‌ی مرجع: v2.0.2** — همه‌ی دستورات زیر از dispatcher و `usage()` خود `ratholectl`/`ratholenode` گرفته شده‌اند.

## نمای سریع (Quick Reference)

| گروه | ratholectl | ratholenode |
|------|-----------|-------------|
| وضعیت | `status` · `ls` · `show` · `info` · `certs` · `paths` · `doctor` · `logs` · `version` | `status` · `show` · `ls` · `logs` · `check` · `doctor` · `version` |
| مدیریت | `add` · `rm` · `edit` · `rename` · `rotate` | `add-svc` · `rm-svc` · `set` · `set-main` · `apply` |
| پیکربندی | `set` · `init` · `regen` · `paths` · `info` | `backup` · `restore` · `migrate` |
| بک‌آپ | `backup` · `restore` · `recover` | `backup` · `restore` |
| حامل تونل | `kcp` · `plain` · `noise` · `backhaul` · `frp` · `gre` | `kcp` · `plain` · `noise` · `backhaul` · `frp` · `gre` |
| ورودی کاربر | `direct` · `proxy` · `game` | — |
| multi-Iran | — | `upstream` · `watchdog` · `adaptive` |
| دامنه/گواهی | `domain` · `cert` · `ip-cert` · `ip-cert-show` · `ip-cert-off` | — |
| مسیر کنترلی | `control-path` | `control-path` · `upstream control-path` |
| Hub/Agent | `hub` · `agent` | `agent` |
| سیستم | `tune` · `fakeweb` · `restart` · `enable` · `update` · `menu` | `tune` · `fakeweb` · `restart` · `update` |

---

## ratholectl — سرور ایران

### وضعیت و اطلاعات

```bash
ratholectl status            # وضعیت سرویس‌ها، پورت‌ها، transport فعال
ratholectl status --json     # داشبورد JSON (برای Hub؛ شامل features هر حامل)
ratholectl version           # نسخه‌ی ratholectl و باینری rathole
ratholectl ls                # لیست نودها با پورت و transport
ratholectl show <name>       # جزئیات و دستور نصب یک نود
ratholectl token <name>      # نمایش دستور نصب (مترادف show)
ratholectl info              # خلاصه‌ی کامل پیکربندی (دامنه، گواهی، پورت‌ها، دامنه‌های SNI)
ratholectl certs             # بررسی انقضای گواهی‌های فعال
ratholectl paths             # نمایش همه‌ی مسیرهای فایل (state، configs، units)
ratholectl doctor            # چک‌لیست سلامت سرویس‌ها، پورت‌ها و تست WS
ratholectl logs [n]          # آخرین n خط لاگ همه سرویس‌ها (پیش‌فرض ۵۰)
ratholectl logs --bundle     # همان، فشرده در یک .txt.gz برای اشتراک‌گذاری
```

### مدیریت نودها

```bash
ratholectl add <name> <inbound_port> [--api-port N]
# افزودن نود؛ دستور نصب کامل را چاپ می‌کند
# --api-port: پورت inbound کانال مدیریت (برای دسترسی hub به نود)

ratholectl rm <name>         # حذف نود و regenerate

ratholectl edit <name> [--inbound N] [--api-port N|off]
# ویرایش پورت inbound یا کانال مدیریت یک نود موجود

ratholectl rename <old> <new>
# تغییر نام نود (= تغییر path کاربری /$old → /$new)
# ⚠ روی نود هم باید service را rename کنید: rm-svc + add-svc

ratholectl rotate <name>
# چرخش توکن نود (و api_token اگر دارد)
# نود باید با توکن جدید دوباره نصب/آپدیت شود
```

### پیکربندی

```bash
ratholectl set domain        <value>   # دامنه اصلی
ratholectl set fullchain     <path>    # مسیر fullchain.pem
ratholectl set key           <path>    # مسیر privkey.pem
ratholectl set nginx-conf    <path>    # مسیر کانفیگ nginx رتهول
ratholectl set fake-port     <N>       # پورت سایت فیک (پیش‌فرض ۸۰۸۰)
ratholectl set sub-port      <N>       # پورت subscription (پیش‌فرض ۲۰۹۶)
ratholectl set control-port  <N>       # پورت کنترل rathole (پیش‌فرض ۲۳۳۳)
ratholectl set sub-path      <seg>     # بخش path برای sub (پیش‌فرض sub)
ratholectl set hub-path      <seg>     # بخش path برای hub (پیش‌فرض hub)
ratholectl regen             # بازتولید server.toml + nginx.conf و hot-reload

ratholectl init              # راه‌اندازی اولیه تعاملی (اگر از install.sh استفاده نشده)
ratholectl init --domain <d> --fullchain <f> --key <k>
# نصب غیرتعاملی (همان flags که install.sh می‌گیرد)
```

### بک‌آپ و بازیابی

```bash
ratholectl backup [file]     # snapshot از state.json + configs (پیش‌فرض /root/rathole-panel-backup-<ts>.tar.gz)
ratholectl restore [file]    # بازگردانی state + configs از backup

ratholectl recover
# حذف همه دامنه‌های اضافی و بازتولید تک‌دامنه — برای رفع خرابی nginx
```

### حامل‌های تونل (Transport)

چهار carrier اول lane رتهول را کنترل می‌کنند؛ Backhaul، FRP و GRE هسته/لین جدا دارند. تغییر carrier مسیر عمومی کاربر و پورت inbound نود را عوض نمی‌کند.

```bash
# KCP — مسیر موازی UDP+FEC
ratholectl kcp on [port] [profile]   # profile: balanced | lossy | aggressive (پیش‌فرض balanced؛ port پیش‌فرض 443)
ratholectl kcp off
ratholectl kcp status
ratholectl kcp show   # کلید و دستور آماده برای نود

# Plain — WebSocket بدون TLS روی پورت HTTP جدا
ratholectl plain on [port]           # پیش‌فرض ۸۸۸۰؛ پورت ۴۴۳ رد می‌شود
ratholectl plain off
ratholectl plain status
ratholectl plain show

# Noise — رمزنگاری X25519 بدون گواهی (اینستنس دوم rathole)
ratholectl noise on [port]           # پیش‌فرض ۲۳۳۴
ratholectl noise off
ratholectl noise status
ratholectl noise show                # چاپ pubkey و خط آماده‌ی نود
ratholectl noise node <name> on      # انتقال این نود به transport=noise
ratholectl noise node <name> off     # برگرداندن نود به transport پیش‌فرض

# Backhaul — مالتی‌پلکس SMUX (هسته‌ی Go جدا، پشت همان nginx/443)
ratholectl backhaul on [port] [transport] [profile] [mode]
# mode: nginx_tls (پیش‌فرض) | direct_ip
# nginx_tls: server transport = ws|wsmux، node = wss|wssmux
# direct_ip: ws|wsmux بدون TLS یا wss|wssmux با گواهی ip-cert
# profile: balanced | lossy | aggressive (باید دو طرف یکی باشد)
ratholectl backhaul off
ratholectl backhaul status
ratholectl backhaul logs
ratholectl backhaul show             # خط آماده‌ی ratholenode backhaul on را چاپ می‌کند
ratholectl backhaul node <name> on   # انتقال نود به transport=backhaul
ratholectl backhaul node <name> off  # برگرداندن نود

# FRP — هسته‌ی ریورس تونل مستقل fatedier/frp
ratholectl frp on [port] [token] [transport]
# پورت پیش‌فرض 7000 (پورت 443 رزرو است)؛ transport: tcp|kcp|quic|websocket (پیش‌فرض tcp)
# اگر به‌جای توکن یک نام transport بدهید، ترانسپورت از همان‌جا خوانده و توکن خودکار ساخته می‌شود
ratholectl frp off                   # خاموش‌کردن frps و پاک‌کردن transport=frp از نودها
ratholectl frp status                # وضعیت فرآیند frps و پورت‌های لوکال
ratholectl frp show [name]           # چاپ دستور آماده کلاینت نود
ratholectl frp node <name> on|off    # انتقال/برگرداندن نود به transport=frp
ratholectl frp ready <name>          # انتظار تا ثبت proxy نود روی 127.0.0.1:<port> (برای هاب/اسکریپت)

# GRE — تونل لایه ۳ نقطه به نقطه کرنل لینوکس (ip tunnel)
ratholectl gre on <remote_ip> [tunnel_ip] [gre_name] # پیش‌فرض tunnel_ip: 10.10.10.1/30, gre1
ratholectl gre off [gre_name]        # حذف اینترفیس مجازی GRE
ratholectl gre status                # بررسی وضعیت اینترفیس GRE
```

**حالت ترکیبی FRP + GRE** دستور واحد ندارد: در پنل هاب با انتخاب حامل `frp+gre` به‌صورت یک‌جا انجام می‌شود (GRE دو طرف + هسته‌ی FRP با `remote` روی آدرس تانل GRE). برای انجام دستی: ابتدا `ratholectl gre on <node_ip>` و `ratholenode gre on <iran_ip> 10.10.10.2`، سپس هسته‌ی FRP را با آدرس تونل GRE فعال کنید.

### ورودی‌های کاربری (Ingress)

> این‌ها **حامل تونل** نیستند — راه ورود جایگزین برای کاربر هستند؛ مسیر تونل بین نود↔ایران دست‌نخورده می‌ماند.

```bash
# Direct-IP — ورود مستقیم به IP سرور با header استتارشده (بدون دامنه/TLS)
ratholectl direct on [--port P] [--header H]
# پیش‌فرض: port=8081، header=X-Cdn-Id؛ مقدار header = نام نود
# ⚠ پورت جدید را در فایروال باز کنید (کد خودش ufw را امتحان می‌کند)
ratholectl direct off
ratholectl direct status
ratholectl direct show [name]    # URL و header آماده برای کاربر

# Proxy — مسیر /<name>/ روی همان 443 به یک upstream دلخواه (بدون عبور از rathole)
ratholectl proxy add <name> <http(s)://host:port>
ratholectl proxy rm <name>
ratholectl proxy ls
```

### Game / SNI (L4 Passthrough)

وقتی یک نود `sni` داشته باشد، پورت ۴۴۳ به حالت stream/SNI nginx (passthrough لایه ۴) می‌رود و vhost لایه ۷ به `internal_port` (پیش‌فرض ۸۴۴۳) منتقل می‌شود.

```bash
ratholectl game add <name> <node_tls_port> <sni>
# name = نام نود روی نود + SNI که کاربر می‌بیند
# node_tls_port = پورتی که Xray/VLESS+TLS روی نود گوش می‌دهد
ratholectl game rm <name>
ratholectl game ls
ratholectl game show <name>
ratholectl game cert <sni>       # دریافت/نمایش گواهی Let's Encrypt برای SNI
```

### مسیر کنترلی مخفی

```bash
ratholectl control-path show          # مسیر /_rh/<hex> جاری (masked در لاگ)
ratholectl control-path rotate [--dry-run]  # ساخت مسیر جدید + بکاپ + health-check + rollback خودکار
ratholectl control-path clear         # بازگشت سازگار به /
```

بعد از `rotate`، مسیر جدید باید روی نودها اعمال شود (مسیر `/` همچنان کار می‌کند و نودهای به‌روزنشده قطع نمی‌شوند):

```bash
ratholenode control-path set '/_rh/<hex32>'                    # روی نود، برای تانل اصلی
ratholenode upstream control-path <id> set '/_rh/<hex32>'      # برای هر سرور ایران جدا
ratholenode control-path clear                                 # یا upstream control-path <id> clear
```

> تغییر `control-path` یک تغییر transport است و restart می‌خواهد؛ هر دو CLI در صورت بالا نیامدن تونل، خودکار rollback می‌کنند. `rotate` پیش‌نیاز پشتیبانی core از `websocket.path` را چک می‌کند (`ratholectl update` در صورت نیاز).

### چند دامنه

```bash
ratholectl domain add <domain> [--certbot] [--email E] [--fullchain F] [--key K]
# دامنه اضافی روی همان سرور؛ اگر گواهی ندارد از گواهی دامنه اصلی استفاده می‌کند
ratholectl domain rm <domain>
ratholectl domain ls
ratholectl domain primary <domain> [--certbot] [--email E] [--fullchain F] [--key K]
# تغییر دامنه اصلی + گواهی آن

# گواهی Let's Encrypt با certbot (تعاملی‌تر از --certbot در domain add)
ratholectl cert <domain> [email]

# گواهی self-signed برای ورود مستقیم به IP (بدون دامنه)
ratholectl ip-cert <IPv4> [days]       # ساخت/بارگذاری گواهی (پیش‌فرض ۸۲۵ روز)
ratholectl ip-cert-show [IP]           # نمایش public cert
ratholectl ip-cert-off                 # حذف vhost IP TLS
```

### Hub

```bash
ratholectl hub on [port]   # نصب خودکار hub اگر نصب نشده + فعال‌سازی پشت nginx/443/hub/
# پورت پیش‌فرض ۸۰۸۸؛ nginx مسیر /hub/ را به 127.0.0.1:port proxy می‌کند
# بار اول install-hub.sh را با HUB_PORT همین پورت اجرا می‌کند (رمز مدیر تعاملی پرسیده می‌شود)
ratholectl hub off         # location /hub/ را از nginx حذف می‌کند (service می‌ماند)
ratholectl hub status      # وضعیت service و port، هشدار اگر port ناهماهنگ باشد
ratholectl hub auto-add    # ثبت خودکار همین سرور در inventory هاب (مترادف add-local)
```

### REST Agent (مدیریت بدون SSH)

```bash
ratholectl agent on [port] [token]   # نصب/فعال‌سازی rathole-agent.service (پیش‌فرض پورت ۸۰۸۹)
# مترادف‌ها: install / start
# توکن: آرگومان > /etc/rathole-agent/token > ساخت خودکار (chmod 600)
# در پایان «API URL» و «Token» را برای ثبت در هاب چاپ می‌کند
ratholectl agent off                 # توقف و حذف unit (مترادف: stop)
ratholectl agent restart
ratholectl agent status              # active/inactive + توکن
ratholectl agent token               # چاپ توکن از فایل
ratholectl agent show [port]         # چاپ API URL + توکن
```

> روی سروری که با `install-panel.sh` نصب شده، `ratholeagent.py` و `install-agent.sh` از قبل در `/usr/local/share/rathole/` هستند و `install-agent.sh` در `/usr/local/bin/` symlink دارد؛ بنابراین `sudo install-agent.sh --role iran [--port 8089] [--token T]` هم بدون دانلود کار می‌کند. برای HTTPS به `ratholeagent.py` گزینه‌های `--tls-cert`/`--tls-key` بدهید؛ در سمت هاب برای گواهی self-signed `RATHOLE_AGENT_INSECURE_SSL=1` یا `insecure_ssl: true` در رکورد inventory همان سرور لازم است.

### سیستم

```bash
ratholectl fakeweb start [port] # سایت فیک روی پورت HTTP داخلی (پیش‌فرض ۸۰۸۰)
ratholectl fakeweb stop
ratholectl fakeweb rm
ratholectl fakeweb status

ratholectl tune                # اعمال تنظیمات sysctl برای عملکرد بهتر (BBR، buffer، ...)

ratholectl restart             # ری‌استارت rathole-server (همه تانل‌ها لحظه‌ای قطع می‌شوند)
ratholectl enable              # enable + start سرویس rathole-server

ratholectl update              # آپدیت به آخرین نسخه‌ی پایدار (snapshot + health-check + rollback خودکار)
ratholectl update beta         # آخرین نسخه‌ی pre-release
ratholectl update stable       # صریحاً کانال پایدار
ratholectl update v2.0.2       # آپدیت به یک نسخه‌ی خاص
ratholectl menu                # منوی تعاملی (پیش‌فرض)
```

---

## ratholenode — نود خارج

### وضعیت و اطلاعات

```bash
ratholenode status           # transport فعال، endpoint، وضعیت service (+ GRE اگر فعال باشد)
ratholenode status --json    # خروجی JSON (main/gre/watchdog/adaptive) برای هاب
ratholenode version          # نسخه‌ی ratholenode
ratholenode show             # محتوای node.env + لیست سرویس‌ها
ratholenode ls               # لیست سرویس‌های ثبت‌شده (با remote port اگر FRP باشد)
ratholenode check            # فقط بررسی تداخل پورت inbound سرویس‌ها با listenerهای نود
ratholenode doctor           # بررسی binary، پشتیبانی core از control-path، سرویس‌ها و upstreamها
```

### مدیریت سرویس

```bash
ratholenode add-svc <name> <token> <inbound_port> [remote_port]
# افزودن سرویس به tunnel؛ از دستور خروجی ratholectl show بگیرید
# remote_port اختیاری است و برای نگاشت پورت سمت ایران (مثلاً FRP) ذخیره می‌شود

ratholenode rm-svc <name>    # حذف سرویس

ratholenode set SERVER <host:port>
# تغییر آدرس سرور ایران (tunnel اصلی)
ratholenode set TLS_HOSTNAME <domain|ip>
ratholenode set TLS_TRUSTED_ROOT <path>
ratholenode set RATHOLE_VERSION <tag>

ratholenode set-main <host:port> [tls_hostname] [trusted_root]
# تنظیم اتمیک سرور + TLS SNI + CA سفارشی (برای direct-IP با ip-cert)
# tls_hostname: نام دامنه برای SNI (اگر با IP وصل می‌شوید)
# trusted_root: مسیر fullchain.pem گواهی self-signed سرور ایران (بدون tls_hostname مجاز نیست)

ratholenode apply            # بازتولید client.toml و hot-reload (بدون restart)
ratholenode logs [n]         # آخرین n خط لاگ tunnel اصلی (پیش‌فرض ۵۰)
ratholenode logs all [n] [--bundle]   # لاگ همه سرویس‌ها + upstreamها؛ --bundle برای .txt.gz
```

### حامل‌های تونل

```bash
ratholenode kcp on <ip:port> <key> [profile]   # profile: balanced|lossy|aggressive
ratholenode kcp off
ratholenode kcp status

ratholenode plain on <ip:port>   # WebSocket بدون TLS
ratholenode plain off
ratholenode plain status

ratholenode noise on <ip:port> <pubkey> [pattern]
ratholenode noise off
ratholenode noise status

ratholenode backhaul on <domain|host:port> <token> [wssmux|wss|wsmux|ws] [profile]
# transport پیش‌فرض wssmux (TLS)؛ دستور آماده را از ratholectl backhaul show بگیرید
ratholenode backhaul add-svc <name> <token> <inbound_port>
ratholenode backhaul rm-svc <name>
ratholenode backhaul ls
ratholenode backhaul off
ratholenode backhaul status
ratholenode backhaul logs

# FRP — کلاینت ریورس تونل frpc (اتصال مستقیم به frps)
ratholenode frp on <iran_ip:port> <token> [transport] [remote_port]
# transport: tcp|kcp|quic|websocket (پیش‌فرض tcp)؛ اگر پورت ندهید 7000 فرض می‌شود
# این دستور tunnel را به حالت FRP می‌برد و client/kcp/backhaul/adaptive قبلی را خاموش می‌کند
ratholenode frp off              # بازگشت به websocket/443
ratholenode frp status

# GRE — رابط نقطه به نقطه لایه ۳ کرنل لینوکس (ip tunnel)
ratholenode gre on <iran_ip> [tunnel_ip] [gre_name]   # پیش‌فرض tunnel_ip: 10.10.10.2/30, gre1
ratholenode gre off [gre_name]
ratholenode gre status
ratholenode gre probe <peer_ip> [gre_name]            # ping از داخل اینترفیس GRE (پروتکل 47/فایروال)
```

### Adaptive Failover (سوئیچ خودکار)

```bash
ratholenode adaptive on [--interval N] [--failures N] [--recoveries N]
# interval: بازه‌ی probe به ثانیه (پیش‌فرض ۳۰)
# failures: تعداد شکست متوالی برای سوئیچ (پیش‌فرض ۳)
# recoveries: تعداد موفقیت متوالی برای بازگشت (پیش‌فرض ۵)
ratholenode adaptive off
ratholenode adaptive status  # transport فعال، نتیجه‌ی آخرین probe
ratholenode adaptive test [--json]  # یک probe اجرا و نتیجه را فوری نشان می‌دهد
ratholenode adaptive run     # اجرای یک دور کنترلر (همان چیزی که timer صدا می‌زند)
```

جزئیات رفتار و محدودیت‌ها: **[Adaptive Filtering](Adaptive-Filtering-Guide)**.

### Upstream — چند سرور ایران

نود می‌تواند هم‌زمان به چند سرور ایران وصل باشد. هر upstream یک `rathole-client@<id>` مستقل است.

```bash
ratholenode upstream add <id> <server:port> [hostname]
ratholenode upstream add-svc <id> <name> <token> <inbound>
ratholenode upstream rm-svc <id> <name>
ratholenode upstream rm <id>
ratholenode upstream apply <id>        # بازتولید client.toml این upstream
ratholenode upstream restart <id>
ratholenode upstream ls                # لیست همه upstreamها + transport هر کدام
ratholenode upstream status <id>
ratholenode upstream logs <id> [n]
ratholenode upstream kcp   <id> on <ip:port> <key> [profile] | off | status
ratholenode upstream plain <id> on <host:port> | off | status
ratholenode upstream noise <id> on <host:port> <pubkey> [pattern] | off | status
ratholenode upstream ws    <id>        # برگشت به transport=ws
ratholenode upstream control-path <id> show | set <path> | clear
```

### Watchdog — راه‌اندازی مجدد خودکار

```bash
ratholenode watchdog on [interval_sec]   # پیش‌فرض ۶۰؛ بازه‌ی مجاز ۵ تا ۳۶۰۰ ثانیه
# یک systemd timer می‌سازد که tunnel گیر‌کرده/قطع را restart می‌کند
ratholenode watchdog off
ratholenode watchdog status
ratholenode watchdog run     # یک دور بررسی (همان چیزی که timer صدا می‌زند)
```

> Watchdog برای lane اصلی از همان probe لایه‌ای Adaptive استفاده می‌کند (`WD_PROBE`، پیش‌فرض روشن؛ `WD_PROBE_FAILS` پیش‌فرض ۳) و فقط وقتی چند probe متوالی ناموفق باشد restart می‌کند تا با jitter شبکه flapping نکند.

### مسیر کنترلی

```bash
ratholenode control-path show           # مسیر جاری (پیش‌فرض /)
ratholenode control-path set <path>     # تنظیم + gen + restart + rollback خودکار
ratholenode control-path clear          # بازگشت به /
```

### REST Agent

```bash
ratholenode agent on [port] [token]   # فعال‌سازی rathole-agent.service با role=node (پیش‌فرض 8089)
# مترادف‌ها: install / start
ratholenode agent off                 # مترادف: stop
ratholenode agent restart
ratholenode agent status
ratholenode agent token
ratholenode agent show [port]
```

### بک‌آپ

```bash
ratholenode backup [file]    # node.env + services.conf + upstreams (پیش‌فرض /root/rathole-node-backup-<ts>.tar.gz)
ratholenode restore <file>   # بازگردانی + بازتولید client.toml + restart
```

### ابزارهای تشخیص

```bash
ratholenode migrate
# نقشه‌ی مهاجرت همه tunnelها (main + upstreamها) به KCP را چاپ می‌کند
# دستورات دو طرف را آماده نشان می‌دهد؛ هیچ تغییری اعمال نمی‌کند
```

### سیستم

```bash
ratholenode tune             # اعمال sysctl برای بهینه‌سازی (BBR، buffer، ...)
ratholenode fakeweb start [port]   # سایت فیک سبک برای fallback inbound (پیش‌فرض ۸۰۸۱)
ratholenode fakeweb stop
ratholenode fakeweb rm
ratholenode fakeweb status
ratholenode restart          # ری‌استارت rathole-client (اگر tunnel=frp باشد، apply می‌کند)
ratholenode update           # آپدیت به آخرین نسخه‌ی پایدار
ratholenode update beta      # آخرین pre-release
ratholenode update v2.0.2    # آپدیت به نسخه‌ی خاص
```

---

## نکات مشترک

**توکن‌ها جدا هستند.** توکن backhaul، توکن هر سرویس رتهول و کلید KCP مستقل‌اند؛ توکن backhaul را با `openssl rand -hex 20` بسازید و فقط به نودهای backhaul بدهید. توکن FRP هم مشترک بین frps/frpc است و از توکن‌های سرویس جداست.

**transport دو طرف backhaul عمداً متفاوت است:** سرور ایران `ws`/`wsmux` (بدون TLS) و نود `wss`/`wssmux` (با TLS) می‌گیرد. `tcpmux` از nginx لایه ۷ عبور نمی‌کند.

**transport دو طرف GRE مکمل است:** ایران `10.10.10.1/30` و نود `10.10.10.2/30` (پیش‌فرض‌ها)؛ MTU 1476 و TCPMSS clamp. فقط بعد از `ip link` UP بودن دلیل عبور پکت نیست — `gre probe` را بزنید.

**lane رتهول یک transport فعال دارد** (`ws`/`kcp`/`plain`/`noise`). Backhaul، FRP و GRE لین/هسته‌ی جدا دارند؛ یک ماشین می‌تواند هم‌زمان سرویس‌های متفاوت را روی چند lane اجرا کند (سرویس‌های Backhaul در `bh-services.conf` و سرویس‌های رتهول در `services.conf`).

**آپدیت همیشه قبل از تغییر یک snapshot کامل می‌گیرد.** در صورت خرابی از `update.sh --rollback` یا `bootstrap.sh --rollback` استفاده کنید؛ `ratholectl update` فقط channel/tag می‌گیرد و مسیر امن update را اجرا می‌کند.

**token نود در نصب یک‌خطی** باید بعد از جداکننده‌ی `--` بیاید (وگرنه `install.sh` آن را توکن GitHub می‌گیرد): `... | sudo bash -s -- --node -- --server ... --token <T> --inbound-port <P>`.
