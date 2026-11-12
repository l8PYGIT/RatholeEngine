# عیب‌یابی، بک‌آپ و رول‌بک

**نسخه‌ی مرجع: v2.0.2** — این صفحه شامل عیب‌یابی تانل، **REST Agent**، ناسازگاری حامل‌ها (Backhaul/FRP/GRE)، آپدیت از مخزن خصوصی و رول‌بک است.

---

## ابزار تشخیص خودکار

```bash
sudo ratholectl doctor      # ایران: سرویس‌ها، پورت‌های لوکال، تست WS به control-path، health
sudo ratholenode doctor     # نود: binary، پشتیبانی core از control-path، سرویس‌ها و upstreamها
sudo ratholenode check      # فقط تداخل پورت inbound سرویس‌ها با listenerهای روی نود
sudo ratholenode adaptive test [--json]   # یک probe آنی از حامل فعلی
```

در هاب هم هر ردیف سرویس دکمه‌ی **«تست سلامت»** دارد که `ratholectl doctor` را روی سرور ایران اجرا و خروجی را نمایش می‌دهد.

---

## بررسی لاگ‌ها

```bash
# ایران — همه سرویس‌ها یکجا (توکن/کلید redact می‌شوند)
sudo ratholectl logs [n]
sudo ratholectl logs --bundle   # فشرده برای اشتراک‌گذاری

# نود خارج
sudo ratholenode logs [n]
sudo ratholenode logs all [n] [--bundle]   # main + upstreamها + سرویس‌ها

# مستقیم از journalctl
sudo journalctl -u rathole-server -n 50 --no-pager
sudo journalctl -u rathole-client -n 50 --no-pager
sudo journalctl -u rathole-backhaul-server -n 50 --no-pager
sudo journalctl -u rathole-backhaul-client -n 50 --no-pager
sudo journalctl -u frps -n 50 --no-pager
sudo journalctl -u frpc -n 50 --no-pager
sudo journalctl -u rathole-agent -n 50 --no-pager
```

> GRE دیمن/systemd unit ندارد (اینترفیس کرنل است)؛ وضعیت آن با `sudo ratholectl gre status` / `sudo ratholenode gre status` و `ip -s link show gre1` بررسی می‌شود.

---

## مشکلات رایج

### tunnel وصل نمی‌شود

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| نود log `retrying` دائمی دارد | آدرس/پورت اشتباه، یا control-path ناهماهنگ | `ratholenode show` → `SERVER` را بررسی کن؛ `ratholectl control-path show` با مقدار `CONTROL_PATH` در نود تطبیق بده |
| `nginx -t` خطا می‌دهد | config دستی ویرایش شده یا regenerate ناقص | `sudo ratholectl regen` → اگر باز هم خطا: `ratholectl recover` |
| نود وصل است ولی ترافیک نمی‌رسد | `map $uri` یا `inbound_port` اشتباه | `ratholectl ls` → port نود با config Xray/VLESS تطبیق بده |
| بعد از `control-path rotate` تانل قطع شد | نود به‌روزرسانی نشده یا core قدیمی است | `ratholenode control-path set '<مسیر>'` و برای هر upstream: `ratholenode upstream control-path <id> set '<مسیر>'`؛ مسیر `/` همیشه سازگار است |

### REST Agent (مدیریت بدون SSH)

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| هاب badge `no_agent` یا `Agent connection error` | سرویس agent خاموش، پورت اشتباه، یا فایروال | `sudo ratholectl agent status`، `journalctl -u rathole-agent -n 30`، سپس `curl -s http://<ip>:8089/api/ping` (بدون auth) |
| ۴۰۱ `Missing Authorization header` یا `Invalid Authorization scheme` | توکن در رکورد هاب خالی/غلط است یا درخواست بدون Bearer می‌رود | رکورد سرور را در هاب Edit کن و `api_token` را بگذار؛ `sudo ratholectl agent token` مقدار درست را می‌دهد |
| ۴۰۳ `Invalid token` | توکن هاب با `/etc/rathole-agent/token` یکی نیست (بعد از reinstall/rotate) | توکن را از agent بخوان و در رکورد سرور به‌روزرسانی کن؛ `ratholectl agent restart` |
| `connection reset`/قطع ناگهانی یا بدنه‌ی بزرگ رد می‌شود | payload باید ۱ بایت تا ۱ مگابایت و `cmd` لیست غیرخالی رشته باشد | اندازه‌ی بدنه و شکل `{"cmd":[...]}` را بررسی کن (سرورهای قدیمی‌تر بدنه را در auth-fail نمی‌خواندند؛ آپدیت کن) |
| `Binary '...' is not permitted` | agent فقط allow-list را اجرا می‌کند | از `ratholectl`/`ratholenode`/`systemctl`/`journalctl`/… (فهرست مجاز) استفاده کن یا action هاب را برای همان کار بساز |
| `Execution timed out` یا `rc:124` | دستور طولانی‌تر از timeout بود (max ۳۶۰۰ ثانیه) | همان دستور را دستی روی سرور اجرا کن؛ برای `doctor`/`update` زمان کافی بده |
| خطای `CERTIFICATE_VERIFY_FAILED` (HTTPS self-signed) | هاب گواهی agent را trust نمی‌کند | در رکورد همان سرور `insecure_ssl: true` بگذار (یا `RATHOLE_AGENT_INSECURE_SSL=1` در محیط هاب)، یا گواهی معتبر نصب کن (`--tls-cert`/`--tls-key`) |
| برای نود REST API فیلدهای IP در GRE خالی است | `public_ip` روی رکورد ثبت نشده و autodetect نشد | در Edit server هاب `public_ip` را دستی بگذار |
| agent بعد از آپدیت خاموش شد | unit فعال نبوده یا توکن جابه‌جا شده | `update.sh` اگر unit موجود باشد آن را ری‌استارت می‌کند و توکن `/etc/rathole-agent/token` را حفظ می‌کند؛ در غیر این صورت `ratholectl agent on` |

### ناسازگاری حامل‌ها (Carrier Mismatch)

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| برچسب حامل `?` | پروتکل از سرور گزارش نشده (overview کهنه/ناقص یا سرور قدیمی) | وضعیت را refresh کن، `ratholectl status --json`/`ratholenode status --json` را چک کن و سرور را آپدیت کن. `?` به‌تنهایی یعنی «گزارش نشده»، نه قطع تانل |
| Backhaul: `control channel` مدام قطع/وصل | دو طرف token متفاوت یا profile ناهماهنگ | `ratholectl backhaul show` و `ratholenode backhaul status` → token/profile/transport دو طرف را یکی کن |
| Backhaul: کلاینت وصل نمی‌شود | transport اشتباه | سرور `ws`/`wsmux` و نود `wss`/`wssmux` — عمداً متفاوتند؛ `tcpmux` روی nginx لایه ۷ کار نمی‌کند |
| Backhaul: probe/doctor با ۴۰۱ خطا می‌دهد | probe بدون هدر `Authorization: Bearer <token>` رفته (نسخه‌ی قدیمی) | آپدیت کن؛ از v2.0.1 probe بک‌هال توکن را می‌فرستد و doctor کد ۴۰۱ را «زنده» حساب می‌کند |
| Backhaul: port bind نمی‌شود | نود هنوز در `server.toml` مانده | `ratholectl backhaul node <name> on` → `regen` |
| Backhaul: سرویس بالا نمی‌آید، لاگ `Usage: ... -c` | نسخه‌ی قدیمی یونیت | آپدیت به **v2.0.2** و اجرای دوباره‌ی `ratholenode backhaul on ...` |
| Backhaul: دو نود با همان `inbound_port` | mapping محلی تکراری | روی یک سرور ایران فقط یک ماشین خارجی به Backhaul وصل شود و inboundها یکتا باشند |
| Backhaul: `rathole-client` روی نود بک‌هال هم فعال است | طبیعی است (dual-core) | در dual-core هر دو client می‌توانند فعال باشند؛ سرویس‌ها در `services.conf` و `bh-services.conf` قاطی نشوند |
| FRP: کلاینت وصل نمی‌شود | transport نود با frps یکی نیست | `ratholectl frp status` (ترانسپورت گزارش‌شده) و `ratholenode frp status`؛ `ratholenode frp on <ip:port> <token> <transport> <remote_port>` را با همان transport دوباره بزن |
| FRP: `frp ready` ثبت proxy را نمی‌بیند | frps فعال نیست، پورت/UDP فایروال بسته است یا `remote_port` غلط است | `systemctl status frps`، `journalctl -u frps`، `ratholectl frp status`؛ برای `kcp`/`quic` پورت UDP را هم در فایروال باز کن |
| FRP: توکن نامعتبر | frps و frpc با توکن متفاوت | `ratholectl frp show` خط آماده‌ی نود را با توکن درست چاپ می‌کند؛ همان را روی نود بزن |
| GRE: `gre probe` شکست می‌خورد | پروتکل ۴۷ (GRE) توسط ارائه‌دهنده/فایروال بسته است یا IP دو طرف اشتباه | روی هر دو سرور پروتکل GRE را inbound/outbound باز کن؛ `ratholectl gre status` و `ratholenode gre status` را مقایسه کن (ایران `10.10.10.1/30` و نود `10.10.10.2/30`) |
| GRE: اتصال برقرار است ولی سایت‌ها باز نمی‌شوند | MTU/MSS یا PMTU | GRE با MTU 1476 و TCPMSS clamp ست می‌شود؛ اگر مسیر MTU کمتری دارد، MTU را پایین‌تر بیاور و `tcp_mtu_probing=1` را چک کن |
| GRE به‌عنوان حامل: سرویس بالا نمی‌آید | listener پلین روی ایران (`8880/tcp`) از داخل تانل GRE در دسترس نیست | `ratholectl plain status` و `ss -ltn 'sport = :8880'`؛ پورت را در فایروال باز کن |
| Noise: اتصال قطع می‌شود | pubkey ناهماهنگ | `ratholectl noise status` → pubkey را کپی و روی نود `ratholenode noise on <ip:port> <pubkey>` بزن |
| KCP: پکت رد می‌شود | پروفایل دو طرف یکی نیست | profile (`balanced`/`lossy`/`aggressive`) را دو طرف یکسان کن |

### Direct-IP

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| کاربر به سایت فیک می‌رود | header وجود ندارد یا نام نود اشتباه | مقدار header باید دقیقاً نام نود باشد (`ratholectl direct show <name>`) |
| پورت direct-IP باز نیست | فایروال | `ufw allow <port>/tcp` (کد خودش تلاش می‌کند) |
| SNI node از direct-IP استفاده نمی‌کند | SNI nodeها L4 passthrough هستند و پورت direct-IP ندارند | این محدودیت ذاتی است |

### Adaptive Failover

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| adaptive سوئیچ نمی‌کند | `kcp` روی سرور ایران فعال نیست | `ratholectl kcp on` روی ایران + `ratholenode kcp on` روی نود |
| adaptive سوئیچ نمی‌کند ولی حامل `plain`/`noise`/`backhaul`/`frp` است | کنترلر فقط بین `ws` و `kcp` سوئیچ می‌کند و برای بقیه هشدار می‌دهد | این رفتار عمدی است؛ انتخاب دستی حامل بر adaptive اولویت دارد |
| adaptive مدام سوئیچ می‌کند | threshold خیلی پایین | `ratholenode adaptive on --failures 5 --recoveries 8 --interval 45` |
| وضعیت `ws_rejected` | control-path ناهماهنگ یا پاسخ غیر‑۱۰۱ از سمت ایران | `ratholectl control-path show` و مقایسه با `node.env/CONTROL_PATH` |

### چند دامنه (domain)

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| `nginx -t` بعد از `domain add` خطا | گواهی پیدا نشد | مسیر `--fullchain` و `--key` را بررسی کن یا از `--certbot` استفاده کن |
| دامنه اضافی کار نمی‌کند | DNS به این سرور اشاره نمی‌کند | DNS را بررسی کن؛ بعد `ratholectl regen` |
| nginx crash loop بعد از `domain add` | `default_server` conflict | `ratholectl recover` → nginx را به‌حالت تک‌دامنه برگرداند |

### گواهی IP (ip-cert)

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| نود با `set-main` به IP وصل نمی‌شود | گواهی self-signed trusted نیست | `ratholectl ip-cert-show <ip>` → cert را در `/etc/rathole/trusted-<ip>.pem` ذخیره کن → `ratholenode set-main <ip>:443 <ip> /etc/rathole/trusted-<ip>.pem` |
| `ip-cert-off` خطا می‌دهد | backhaul direct_ip با wss/wssmux از همین گواهی استفاده می‌کند | اول backhaul را به `wsmux` تغییر بده |

### آپدیت، رول‌بک و مخزن خصوصی

| نشانه | علت | راه‌حل |
|-------|-----|---------|
| `download install.sh az hameye mirror-ha shekast khord` | فیلترینگ، slug اشتباه، یا release موجود نیست | `RATHOLE_GH` را چک کن؛ `ratholectl update v2.0.2` را امتحان کن؛ از `--token` برای مخزن خصوصی استفاده کن |
| آپدیت از مخزن خصوصی دانلود نمی‌شود | برای مخزن خصوصی mirrorهای عمومی استفاده نمی‌شوند و توکن لازم است | `install.sh --token <PAT> ...` یا `RATHOLE_GH_TOKEN=...`؛ توکن باید دسترسی `Contents: read` داشته باشد. برای سرور نصب‌شده: `sudo RATHOLE_GH=owner/repo bash tools/update-private.sh` |
| نصب نود توکن را نمی‌گیرد / `--token` نادیده گرفته می‌شود | `install.sh` هر `--token` قبل از `--` را توکن GitHub می‌گیرد | آرگومان‌های نود را بعد از جداکننده بده: `... \| sudo bash -s -- --node -- --server ... --token <T> --inbound-port <P>` (باگ post-2.0.2 اصلاح شد) |
| update با `rc` غیرصفر تمام شد ولی سرور کار می‌کند | health-check یا نصب فایل ناموفق بوده | `sudo update.sh --list-backups` → `sudo update.sh --rollback [<ts>]`؛ سپس `journalctl -u rathole-server -n 30` |
| آپدیت به‌صورت خودکار برگشت خورد | `nginx -t` یا سرویس رول health-check را رد کرد | snapshot خودکار بازگردانده شده؛ لاگ health را بخوان و علت را برطرف کن |
| به‌روزرسانی روی سرور agent را از کار انداخت | unit فعال نبود/توکن legacy در unit بود | `update.sh` فایل‌های agent را refresh، توکن را حفظ و unit را ری‌استارت می‌کند؛ در صورت نیاز `ratholectl agent on` |

---

## بک‌آپ و رول‌بک

### آپدیت با بک‌آپ خودکار

`update.sh` (که `ratholectl update`/`ratholenode update` و دکمه‌ی هاب هم آن را صدا می‌زنند) قبل از هر تغییر یک snapshot کامل (CLI + configs + systemd units) در `/var/backups/rathole-manager/pre-update-<ts>/` می‌گیرد، health-check می‌زند و در صورت شکست خودکار rollback می‌کند. نگه‌داری ۷ snapshot آخر (`RATHOLE_BACKUP_RETENTION`).

```bash
ratholectl update      # snapshot کامل → آپدیت → health-check → رول‌بک خودکار در صورت شکست
ratholenode update
```

### مدیریت دستی بک‌آپ‌ها

```bash
# ایران
sudo ratholectl backup [file]       # snapshot از state + configs
sudo ratholectl restore [file]

# نود
sudo ratholenode backup [file]      # node.env + services + upstreamها
sudo ratholenode restore <file>

# رول‌بک از snapshot آپدیت
sudo update.sh --list-backups
sudo update.sh --rollback                         # آخرین snapshot سالم
sudo update.sh --rollback 20261016-094447         # یک snapshot خاص
sudo update.sh --no-rollback                      # snapshot بگیر ولی خودکار برنگردان
```

### بک‌آپ nginx (داخل regenerate)

هر بار که `regenerate` موفق می‌شود، یک `.rathole-good.bak` از config nginx ذخیره می‌شود. اگر `nginx -t` شکست بخورد، همان فایل خودکار بازگردانده می‌شود.

```bash
sudo ratholectl recover    # حذف همه دامنه‌های اضافی + بازتولید تک‌دامنه
```

---

## همچنین ببینید

- **[مرجع کامل CLI](CLI-Reference)** — syntax دقیق همه دستورات
- **[راهنماهای عملی](Workflow-Guides)** — گام‌به‌گام: REST Agent، تغییر حامل، مهاجرت Backhaul/Noise، direct-IP، چند دامنه، multi-upstream، آپدیت مخزن خصوصی
- **[Adaptive Filtering](Adaptive-Filtering-Guide)** — منطق probe و سوئیچ خودکار
