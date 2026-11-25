# ratholehub — پنل وب مدیریت (REST API + UI)

پنل مرکزی برای مدیریت چند سرور ایران و چند نود، بدون تداخل با سیستم فعلی. هاب از سه روش اتصال پشتیبانی می‌کند: **SSH با کلید** (پیش‌فرض)، **REST Agent** توکن‌دار (بدون SSH) و **Reverse WebSocket Agent (`reverse_ws`)** برای نودهای فیلترشده/پشت NAT بدون نیاز به هیچ پورت ورودی باز. توضیح کامل UI و API در `docs/hub.md` است.

## چرا این طراحی
- **SSH پیش‌فرض، Agent مستقیم یا معکوس (Reverse WS):** پنل فقط روی یک سرور (معمولاً rp01) نصب می‌شود و از طریق **SSH با کلید** همان `ratholectl`/`ratholenode` تست‌شده را روی بقیه اجرا می‌کند؛ اگر SSH ممکن نبود، `ratholeagent.py` (نسخه `2.0.0`) می‌تواند با REST توکن‌دار (پورت `8089`) گوش دهد یا با `wsutil.py` به‌صورت خروجی از سمت سرور مقصد به `/hub/ws/agent` (پورت ۴۴۳ Nginx) وصل شود.
- **بدون وابستگی pip**: هاب، Agent و ماژول RFC 6455 (`wsutil.py`) فقط پایتون stdlib هستند. با هیچ‌چیز روی سرور تداخل نمی‌کنند.
- **REST API توکن‌دار**: برای اتصال ابزارهای دیگر/اتوماسیون و کنترل وضعیت.
- **امن**: روی `127.0.0.1` می‌شنود؛ دسترسی از طریق SSH-forward یا nginx زیر همان دامنه (یک پورت/یک دامنه حفظ می‌شود).

## نصب
```bash
cd rathole-manager/ratholehub
sudo bash install-hub.sh          # رمز مدیریت می‌پرسد، API TOKEN تولید می‌کند
```

یا از روی خود سرور ایران (بار اول نصب خودکار، دفعات بعد همگام‌سازی پورت):
```bash
sudo ratholectl hub on 8088       # → https://<domain>/hub/
```

نصاب کل درخت را کپی می‌کند: `hub.py` (روتر/وضعیت/SSH/Agent)، **`hubcmds.py`** (نقشه‌ی امنیتی action→argv — بدون این فایل هاب بالا نمی‌آید) و پوشه‌ی **`ui/`** (`index.html`، `app.css`، `app.js`، `i18n.js`، `vazirmatn.woff2`). `update.sh` هم هنگام آپدیت نقش هاب همه را به‌روز می‌کند.
پیش‌نیاز SSH (اگر از حالت Agent استفاده نمی‌کنید): از سرور پنل به بقیه سرورها SSH با کلید ست باشد:
```bash
ssh-copy-id root@<node_ip>
```
اگر هاب با `ratholectl hub on` روی همان ایران بالا بیاید، سرور لوکال (`iran-main` روی `127.0.0.1`) خودکار در inventory ثبت و کلید هاب همان‌جا authorize می‌شود.

## دسترسی
امن‌ترین (بدون باز کردن پورت) — از سیستم خودت:
```bash
ssh -L 8088:127.0.0.1:8088 root@<rp01_ip>
# مرورگر:  http://localhost:8088
```

## رابط کاربری (v2.4.0)
- **Reverse WebSocket (`reverse_ws`) و تبدیل سرورهای آفلاین:** در فرم افزودن سرور گزینهٔ `reverse_ws` توکن و دستور اتصال یک‌خطی را در مودال آماده می‌کند؛ در صفحهٔ سرورهای آفلاین REST API نیز دکمهٔ تبدیل یک‌کلیکی به `reverse_ws` نمایش داده می‌شود (همراه با badge وضعیت آنلاین/در انتظار و `rotate_token`).
- **صفحهٔ تستر و تیونر شبکه (`#/tuner`) و وضعیت زنده کرنل:** اجرای ۶ مرحله‌ای `rathole-tuner` با ماندگاری جاب‌ها هنگام رفرش، کارت وضعیت زنده کرنل (`GET /api/tuner/status`)، پروفایل‌های `rthprof1:`/JSON، تست A/B و اعمال دوفازه‌ای ایمن با Watchdog ددمن (`--confirm-ttl 45` + `bench confirm` و بازگشت فوری ایران در صورت شکست نود).
- **طراحی شیشه‌ای Apple Glass (آفلاین و بدون CDN):** باندل فونت متغیر **`vazirmatn.woff2`**، تم سه‌حالتهٔ **روشن / تاریک / هماهنگ با سیستم**، مودال‌های native `<dialog>`، **۴ کارت KPI** در داشبورد، **نوار جستجو و فیلتر زنده**، **پالت فرمان `⌘K / Ctrl+K`** و بارگذاری موازی سریع‌تر وضعیت سرورها (همراه با کش کوتاه‌مدت TTL).
- **صفحه‌ها**: `#/dashboard` (۴ کارت KPI، نوار وضعیت هاب، فیلتر/کارت/فهرست سرورها، Provision/`reverse_ws`، آپدیت همه)، `#/server/<name>` (ایران: ۴ تب نودها/حامل‌ها/شبکه/نگهداری + جستجوی زنده، دامنه، Ports، ingress؛ نود: تونل اصلی، Paqet، Managed Xray، جدول یکپارچهٔ سرویس‌ها، ابزارهای `reverse_ws`، upstream)، `#/tuner`، `#/routing` (**فقط‌خواندنی**: گراف SVG قابل جابه‌جایی، جدول، کنسول)، `#/audit` (با جستجوی زنده)، `#/settings` (تم، زبان، پروکسی، TOTP 2FA، توکن‌های RBAC، مانیتور و ربات تلگرام، رله Ed25519، چرخش توکن و رمز).
- **سلکتور حامل در ردیف هر نود (صفحه‌ی ایران، v2.0.4+)**: انتخاب حامل همان نود از داخل جدول — یک تأیید، اعمال **دوطرفه (ایران + نود)** با پارامترهای خودکار، پیام صریح نتیجهٔ همگام‌سازی و بازگشت سلکتور در صورت شکست سمت نود. برای `frp`/`gre`/`frp_gre` مودال کامل باز می‌شود.
- **کنترل سرویس‌ها (منوی ⋯ هر ردیف)**: در ردیف هر سرویس — هم ایران و هم نود — دکمه‌ی **⋯** این پنج اکشن را باز می‌کند: «حامل و پروتکل» (فرم کامل)، «تست سلامت» (`doctor` روی ایران)، «ساخت کانفیگ VLESS» (با UUID واقعی کاربر Xray + دامنه/IP عمومی ایران)، «مدیریت سمت مقابل» و «حذف از دو سمت». لینک قدیمی `#/wiring` به داشبورد برمی‌گردد.
- **برچسب حامل + پروتکل واقعی**: مثل `FRP / QUIC`، `FRP / TCP`، `Backhaul / WSMUX`، `KCP / UDP · balanced`؛ `?` یعنی پروتکل از سرور گزارش نشده. برچسب به‌تنهایی تضمین اتصال نیست؛ تست سلامت ملاک است.
- **تغییر حامل**: پورت اینباند موجود حفظ می‌شود؛ Backhaul رجیستری جدا (`bh-services.conf`) دارد؛ **ترانسپورت انتخابی FRP (`tcp|kcp|quic|websocket`) پس از `frp off` حفظ می‌شود** تا بازگشت به FRP همان مد قبلی را بالا بیاورد؛ حامل اصلی بین سرویس‌های Rathole یک نود مشترک است.
- **دو registry سرویس** — `services.conf` برای lane رتهول و `bh-services.conf` برای Backhaul؛ جدول و actionهای جدا، بدون خاموش‌کردن `rathole-client` هنگام روشن‌شدن Backhaul.
- **routing فقط‌خواندنی** — چیدمان گراف در مرورگر ذخیره می‌شود؛ تغییر مسیر از صفحه‌ی سرور/نود.
- **لاگ قابل دریافت** — خروجی بلند در modal قابل کپی باز می‌شود و logها به فایل متنی دانلود می‌شوند.
- **دکمهٔ «آپدیت همه»** + **badge نسخه** (سبز = هم‌سان با `latest_version` هاب، قرمز/زرد = قدیمی).
- **«افزودن به نود»** (token/inbound از `nodeconnect` → `add_svc`/`upstream_add_svc`) و **«تنظیم تانل اصلی»** (`set_server`/`set_main`).

## REST و Reverse WS Agent (بدون SSH)
```bash
# حالت REST مستقیم روی سرور مقصد (پورت ۸۰۸۹)
sudo install-agent.sh --role node --port 8089
sudo ratholectl agent on 8089 [TOKEN]
sudo ratholenode agent on 8089 [TOKEN]

# حالت Reverse WebSocket (بدون هیچ پورت ورودی باز، مناسب نود فیلترشده/پشت NAT)
sudo ratholenode agent reverse "wss://<DOMAIN>/hub/ws/agent" "<NAME>" "<TOKEN>" [--insecure-ssl] [--proxy <url>]
sudo ratholectl agent reverse "wss://<DOMAIN>/hub/ws/agent" "<NAME>" "<TOKEN>" [--insecure-ssl] [--proxy <url>]
sudo install-agent.sh --role node --reverse "wss://<DOMAIN>/hub/ws/agent" --name "<NAME>" --token "<TOKEN>"

sudo ratholectl agent status|token|show|restart|off
```
`install-panel.sh`/`install-node.sh` از قبل `ratholeagent.py`، `wsutil.py` و `install-agent.sh` را در `/usr/local/share/rathole/` می‌گذارند و `install-agent.sh` را در `/usr/local/bin/` سیم‌لینک می‌کنند؛ `update.sh` هر سه را snapshot و به‌روز می‌کند، توکن را حفظ می‌کند و ری‌استارت از داخل agent را با `_schedule_agent_restart` خارج از cgroup انجام می‌دهد. unit روی هر دو نقش `rathole-agent.service` است (`StartLimitIntervalSec=0`، `LimitNOFILE=65535`، `KillMode=process`).
- `GET /api/ping` → `{ok, role, version: "2.0.0", hostname}` (بدون احراز هویت)؛ در REST server صف `request_queue_size = 64`، TCP keepalive و `TCP_NODELAY` فعال است.
- `POST /api/exec` با `Authorization: Bearer <token>` و بدنه `{"cmd":["ratholectl","status","--json"],"timeout":120}` → `{ok, rc, out, err}`. در حالت `reverse_ws` همین argv با اتصال خروجی از نود روی `/hub/ws/agent` یا `/ws/agent` از طریق `wsutil.py` (سقف فریم ۴ MiB، `ThreadPoolExecutor(16)`) جابه‌جا می‌شود.
- توکن در `/etc/rathole-agent/token` (chmod 600؛ اجرای agent بدون توکن ممکن نیست)؛ احراز هویت با compare ثابت‌زمان (401/403)؛ بدنه ۱ بایت تا ۱ مگابایت؛ `cmd` لیست غیرخالی رشته‌ها؛ timeout ۱–۳۶۰۰ ثانیه؛ **لیست‌سفید محدود باینری** (`ratholectl`، `ratholenode`، `systemctl`، `journalctl`، `jq`، `tail`؛ مسیرهای دارای `/` مسدوداند) — اجرا مستقیم argv، بدون شل.
- HTTPS با `--tls-cert`/`--tls-key` (یا `/etc/rathole-agent/cert.pem` + `key.pem`)؛ برای گواهی self-signed در حالت `api` روی هاب `insecure_ssl: true` یا `RATHOLE_AGENT_INSECURE_SSL=1` بگذارید و در حالت `reverse_ws` پرچم `--insecure-ssl` را به کلاینت بدهید.
- رکورد هاب: `{"name","role","transport":"api","api_url","api_token","insecure_ssl"?,"proxy"?}` یا `{"name","role","transport":"reverse_ws","api_token"}`. همه‌ی actionها همچنان از allow-list `hubcmds.py` عبور می‌کنند و نوشتن‌ها در audit ثبت می‌شوند.

## REST API (نمونه)
همه‌ی مسیرهای `/api/*` هدر `Authorization: Bearer <API_TOKEN>` (یا کوکی نشست `rhsession` از UI) می‌خواهند؛ فقط `GET /api/health` عمومی است و `GET /ws/agent` (و `/hub/ws/agent`) با توکن سرور احراز هویت می‌شود.
```
GET    /api/health
GET    /ws/agent | /hub/ws/agent    ارتقای RFC 6455 برای Reverse WS Agent
POST   /api/login                     {"password":"..."} → {ok, token} + کوکی نشست
GET    /api/hubstatus                 وضعیت هاب + latest_version
GET    /api/servers                   لیست سرورها + وضعیت نشست reverse_ws
POST   /api/servers                   {name,role(iran|node),transport(ssh|api|reverse_ws),...}
PUT    /api/servers/<name>            ویرایش رکورد inventory (+ rotate_token)
DELETE /api/servers/<name>            حذف و بستن نشست فعال reverse_ws
POST   /api/provision                 نصب خودکار با رمز SSH (کلید + deploy + ثبت)
POST   /api/servers/<name>/action     {"action":"...","args":{...}}
GET    /api/servers/<name>/status     چند بررسی read-only (doctor/kcp/plain/noise/backhaul/...)
GET    /api/servers/<name>/overview   خلاصه + نسخه + carrierها + status
GET    /api/servers/<name>/discover   نودهای تعریف‌شده روی ایران
GET    /api/servers/<name>/details    خروجی تشخیصی
GET    /api/servers/<name>/frpconnect      داده‌ی autofill FRP
GET    /api/servers/<name>/kcpconnect      داده‌ی autofill KCP
GET    /api/servers/<name>/noiseconnect    داده‌ی autofill Noise
GET    /api/servers/<name>/backhaulconnect داده‌ی autofill Backhaul
GET    /api/servers/<name>/paqetconnect    داده‌ی autofill Paqet
GET    /api/servers/<name>/mainconnect     داده‌ی autofill تونل اصلی
GET    /api/servers/<iran>/nodeconnect/<node>  token/inbound واقعی نود ایران
POST   /api/tuner/start | GET /api/tuner/jobs | GET /api/tuner/status | GET/POST /api/tuner/profiles | POST /api/tuner/apply|rollback
GET    /api/config                    پیکربندی redact‌شده
POST   /api/config                    چرخش توکن/تغییر رمز مدیر/پروکسی
GET    /api/audit?limit=N             لاگ فعالیت (۱..۵۰۰؛ پیش‌فرض ۱۰۰)
POST   /api/ip-tls/prepare            آماده‌سازی IP-TLS برای نود
```
- `action=status` روی سرور ایران خروجی کامل JSON داشبورد را می‌دهد (`ratholectl status --json`).
- `overview` هر سرور فیلد `version` (`manager` و `rathole`) دارد که در UI با `latest_version` هاب مقایسه می‌شود.
- `/api/servers/<iran>/nodeconnect/<node>`: توکن در `ls` ماسک است؛ از `ratholectl show <node>` گرفته می‌شود.
نمونه:
```bash
TOKEN=... ; B=http://localhost:8088
curl -s -H "Authorization: Bearer $TOKEN" $B/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST $B/api/servers/rp01/action \
  -d '{"action":"kcp_on","args":{"port":"443","profile":"balanced"}}'
```

## توپولوژی: فقط یک هاب
- **یک هاب کافی است** — نیازی به هاب روی هر ایران نیست.
- هاب برای مدیریت، مستقیم با **SSH** (پورت ثبت‌شده در inventory، پیش‌فرض ۲۲)، **REST Agent** (پورت `8089`) یا **Reverse WebSocket (`reverse_ws`)** (اتصال خروجی نود به هاب روی `/hub/ws/agent`) با هر سرور ارتباط می‌گیرد؛ کاملاً مستقل از توپولوژی تونل.
- اینکه یک نود به دو (یا چند) ایران وصل باشد ربطی به هاب ندارد؛ هاب هر سرور را جدا و مستقیم می‌بیند.
- تنها شرط: در `ssh`/`api` هاب به سرور مقصد دسترسی داشته باشد، یا در `reverse_ws` سرور مقصد بتواند به دامنه/پورت هاب اتصال خروجی بزند.

## action های مجاز (whitelist، بدون شل دلخواه)
نگاشت action→argv در **`hubcmds.py`** است؛ هر action تازه باید هم به `build_*_cmd` مربوطه و هم به allow-list اضافه شود و هر آرگومانش با regex (خانواده‌ی `RE_*`) اعتبارسنجی شود.
- **مشترک**: `deploy` (در خود سرور `install.sh --update` از GitHub + snapshot/rollback، حتی روی `reverse_ws`)، `status`, `version`, `logs`, `bench_apply`, `bench_confirm`, `bench_rollback`, `bench_status`.
- **iran**: `ls`, `doctor`, `tune`, `regen`, `restart`, `paths`, `set_config{key,value}`, `backup`, `enable`, `hub_status`؛ transport: `kcp_*`, `plain_*`, `noise_*`, `backhaul_*`, `frp_*`, `gre_*`, `direct_*`؛ دامنه/TLS: `tls_info`, `tls_certs`, `tls_cert`, `domain_*`؛ game/SNI: `game_ls|add|rm|show|cert`؛ نود: `add_node`, `rm_node`, `edit_node`, `rename_node`, `rotate_node`, `show_node`؛ ریورس‌پروکسی غیرتونلی: `proxy_ls|add|rm`.
  - `game_cert` گواهی Let's Encrypt می‌گیرد و خروجی شامل **کلید خصوصی** است؛ فقط از هابِ احرازشده استفاده کن و لاگ نگه ندار.
  - `set_config` علاوه‌بر `domain`/`fullchain`/`key`/`nginx-conf`، پورت‌های `fake-port`/`sub-port`/`control-port` و `sub-path`/`hub-path` را هم می‌پذیرد (این پورت‌ها در بخش مستقل **Ports** صفحه‌ی سرور هم قابل ویرایش‌اند).
- **node**: `show`, `ls`, `status`, `logs`, `upstream_ls`, `set_server`, `set_main`, `control_path_*`, `migrate`, `tune`, `apply`, `restart`, `version`؛ سرویس: `add_svc`, `rm_svc`, `add_bh_svc`, `rm_bh_svc`؛ transport: `kcp_*`, `plain_*`, `noise_*`, `backhaul_*`, `frp_*`, `gre_*`؛ upstream: `upstream_add|add_svc|rm|rm_svc|kcp_*|plain_*|noise_*|ws|apply|restart|logs|status`؛ watchdog/adaptive: `watchdog_*`, `adaptive_*`.
- کشف: `GET /api/servers/<iran>/discover` → لیست نودهای تعریف‌شده در state آن ایران.

UI هنگام باز شدن، وضعیت همه‌ی سرورها را خودکار بارگذاری می‌کند. همه‌ی ورودی‌ها با regex سخت اعتبارسنجی می‌شوند (ضد تزریق).

## مدل امنیتی
- هاب هرگز رشته‌ی خام اجرا نمی‌کند: allow-list action + اعتبارسنجی regex + argv لیستی؛ روی SSH به‌صورت shell-safe (shlex)، روی REST Agent به‌صورت آرایه‌ی JSON به `/api/exec` و روی `reverse_ws` از طریق فریم RFC 6455 (سقف ۴ MiB).
- `WRITE_ACTIONS` actionهای نوشتاری را علامت می‌زند؛ همان‌ها + `deploy`/`provision`/`config_save` در audit log (`/etc/ratholehub/audit.log`، append-only) ثبت می‌شوند.
- روی `127.0.0.1` می‌شنود؛ ورود مدیر محدود به ۵ تلاش ناموفق در ۵ دقیقه برای هر IP؛ کوکی نشست = `hmac(api_token, expiry)` با اعتبار ۲۴ ساعت.
- `deploy_to_server` روی خود سرور آخرین `install.sh` را از GitHub (با حلقه‌ی mirror ghproxy) می‌گیرد؛ فقط `gh_repo` (اعتبارسنجی `RE_SLUG`) و `update_channel` (`stable|beta`) داخل دستور ثابت `bash -c` جای‌گذاری می‌شوند.

## وضعیت
پیاده‌سازی‌شده: مدیریت inventory با سه مسیر **SSH**، **REST Agent** و **Reverse WebSocket (`reverse_ws`)**، وضعیت زنده، actionهای امن با whitelist، مدیریت laneهای rathole/Backhaul/FRP/GRE/Paqet و Managed Xray، تیونر ۶ مرحله‌ای `rathole-tuner` با Watchdog دوفازه‌ای (`--confirm-ttl 45` + `bench confirm`)، افزودن/حذف نود و سرویس، کنترل سرویس‌ها (حامل/پروتکل، تست سلامت، VLESS، مدیریت peer، حذف دوطرفه)، routing graph/table/console فقط‌خواندنی، جمع‌آوری log، آپدیت تک‌سرور/همه و badge نسخه.
