# ratholehub — پنل وب مدیریت (REST API + UI)

پنل مرکزی برای مدیریت چند سرور ایران و چند نود، بدون تداخل با سیستم فعلی. هاب به‌طور پیش‌فرض از طریق **SSH با کلید** کار می‌کند و به‌صورت اختیاری می‌تواند با **REST Agent** توکن‌دار (بدون SSH) هم صحبت کند. توضیح کامل UI و API در `docs/hub.md` است.

## چرا این طراحی
- **SSH پیش‌فرض، Agent اختیاری**: پنل فقط روی یک سرور (معمولاً rp01) نصب می‌شود و از طریق **SSH با کلید** همان `ratholectl`/`ratholenode` تست‌شده را روی بقیه اجرا می‌کند؛ هیچ پورت/سرویس جدیدی روی نودها باز نمی‌شود. اگر SSH ممکن نبود، `ratholeagent.py` روی سرور نصب می‌شود و هاب همان argvها را از طریق REST توکن‌دار (پیش‌فرض `8089`) اجرا می‌کند.
- **بدون وابستگی pip**: هاب و Agent فقط پایتون stdlib هستند. با هیچ‌چیز روی سرور تداخل نمی‌کنند.
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

نصاب کل درخت را کپی می‌کند: `hub.py` (روتر/وضعیت/SSH/Agent)، **`hubcmds.py`** (نقشه‌ی امنیتی action→argv — بدون این فایل هاب بالا نمی‌آید) و پوشه‌ی **`ui/`** (`index.html`، `app.css`، `app.js`، `i18n.js`). `update.sh` هم هنگام آپدیت نقش هاب همه را به‌روز می‌کند.
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

## رابط کاربری (v2.0.2)
- **صفحه‌ها**: `#/dashboard` (کارت/فهرست سرورها، Provision، آپدیت همه، وضعیت هاب)، `#/server/<name>` (ایران: ۴ تب نودها/حامل‌ها/شبکه/نگهداری + دامنه، Ports، ingress؛ نود: تونل اصلی، جدول یکپارچهٔ سرویس‌ها، upstream)، `#/routing` (**فقط‌خواندنی**: گراف SVG قابل جابه‌جایی، جدول، کنسول)، `#/audit`، `#/settings`.
- **کنترل سرویس‌ها (جای بورد سیم‌کشی حذف‌شده)**: در ردیف هر سرویس — هم ایران و هم نود — دکمه‌های «حامل و پروتکل»، «تست سلامت» (`doctor` روی ایران)، «ساخت کانفیگ VLESS» (با UUID واقعی کاربر Xray + دامنه/IP عمومی ایران)، «مدیریت سمت مقابل» و «حذف از دو سمت». لینک قدیمی `#/wiring` به داشبورد برمی‌گردد.
- **برچسب حامل + پروتکل واقعی**: مثل `FRP / QUIC`، `FRP / TCP`، `Backhaul / WSMUX`، `KCP / UDP · balanced`؛ `?` یعنی پروتکل از سرور گزارش نشده. برچسب به‌تنهایی تضمین اتصال نیست؛ تست سلامت ملاک است.
- **تغییر حامل**: پورت اینباند موجود حفظ می‌شود؛ Backhaul رجیستری جدا (`bh-services.conf`) دارد؛ حامل اصلی بین سرویس‌های Rathole یک نود مشترک است. بازگشت خودکار کامل برای همه‌ی ترکیب‌های حامل تضمین نشده است.
- **دو registry سرویس** — `services.conf` برای lane رتهول و `bh-services.conf` برای Backhaul؛ جدول و actionهای جدا، بدون خاموش‌کردن `rathole-client` هنگام روشن‌شدن Backhaul.
- **routing فقط‌خواندنی** — چیدمان گراف در مرورگر ذخیره می‌شود؛ تغییر مسیر از صفحه‌ی سرور/نود.
- **لاگ قابل دریافت** — خروجی بلند در modal قابل کپی باز می‌شود و logها به فایل متنی دانلود می‌شوند.
- **دکمهٔ «آپدیت همه»** + **badge نسخه** (سبز = هم‌سان با `latest_version` هاب، زرد = قدیمی).
- **«افزودن به نود»** (token/inbound از `nodeconnect` → `add_svc`/`upstream_add_svc`) و **«تنظیم تانل اصلی»** (`set_server`/`set_main`).

## REST Agent (بدون SSH)
```bash
# روی سرور مقصد (root؛ python3 لازم است) — role خودکار تشخیص داده می‌شود
sudo install-agent.sh --role node --port 8089
# یا از CLI نصب‌شده:
sudo ratholectl agent on 8089 [TOKEN]
sudo ratholenode agent on 8089 [TOKEN]
sudo ratholectl agent status|token|show|restart|off
```
`install-panel.sh`/`install-node.sh` از قبل `ratholeagent.py` و `install-agent.sh` را در `/usr/local/share/rathole/` می‌گذارند و `install-agent.sh` را در `/usr/local/bin/` سیم‌لینک می‌کنند؛ `update.sh` هر دو را به‌روز می‌کند و توکن را حفظ می‌کند. unit روی هر دو نقش `rathole-agent.service` است.
- `GET /api/ping` → `{ok, role, version, hostname}` (بدون احراز هویت).
- `POST /api/exec` با `Authorization: Bearer <token>` و بدنه `{"cmd":["ratholectl","status","--json"],"timeout":120}` → `{ok, rc, out, err}`.
- توکن در `/etc/rathole-agent/token` (chmod 600)؛ احراز هویت با compare ثابت‌زمان (401/403)؛ بدنه ۱ بایت تا ۱ مگابایت؛ `cmd` لیست غیرخالی رشته‌ها؛ timeout ۱–۳۶۰۰ ثانیه؛ **لیست‌سفید باینری** (ratholectl، ratholenode، bash، python3، python، systemctl، journalctl، curl، jq، cat، tail، ls) — اجرا مستقیم argv، بدون شل.
- HTTPS با `--tls-cert`/`--tls-key` (یا `/etc/rathole-agent/cert.pem` + `key.pem`)؛ برای گواهی self-signed در رکورد هاب `insecure_ssl: true` یا روی هاب `RATHOLE_AGENT_INSECURE_SSL=1`.
- رکورد هاب: `{"name","role","transport":"api","api_url","api_token","insecure_ssl"?,"proxy"?}`. `api_url` فقط `http(s)://host[:port]`. همه‌ی actionها همچنان از allow-list `hubcmds.py` عبور می‌کنند و نوشتن‌ها در audit ثبت می‌شوند. Agent پیش‌فرض روی `0.0.0.0` گوش می‌دهد؛ پورت `8089` و توکن را محدود کنید.

## REST API (نمونه)
همه‌ی مسیرها هدر `Authorization: Bearer <API_TOKEN>` (یا کوکی نشست `rhsession` از UI) می‌خواهند؛ فقط `GET /api/health` عمومی است. همین مسیرها با پیشوند `/hub/api/...` هم پذیرفته می‌شوند.
```
GET    /api/health
POST   /api/login                     {"password":"..."} → {ok, token} + کوکی نشست
GET    /api/hubstatus                 وضعیت هاب + latest_version
GET    /api/servers                   لیست سرورها
POST   /api/servers                   {name,role(iran|node),transport(ssh|api),...}
PUT    /api/servers/<name>            ویرایش رکورد inventory
DELETE /api/servers/<name>
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
GET    /api/servers/<name>/mainconnect     داده‌ی autofill تونل اصلی
GET    /api/servers/<iran>/nodeconnect/<node>  token/inbound واقعی نود ایران
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
- هاب برای مدیریت، مستقیم با **SSH** (پورت ثبت‌شده در inventory، پیش‌فرض ۲۲) یا **REST Agent** (پیش‌فرض پورت `8089`) به هر سرور وصل می‌شود؛ کاملاً مستقل از توپولوژی تونل.
- اینکه یک نود به دو (یا چند) ایران وصل باشد ربطی به هاب ندارد؛ هاب هر سرور را جدا و مستقیم می‌بیند.
- تنها شرط: هاب به هر سروری که در inventory دارد دسترسی داشته باشد (کلید SSH یا Agent).

## action های مجاز (whitelist، بدون شل دلخواه)
نگاشت action→argv در **`hubcmds.py`** است؛ هر action تازه باید هم به `build_iran_cmd`/`build_node_cmd` و هم به allow-list اضافه شود و هر آرگومانش با regex (خانواده‌ی `RE_*`) اعتبارسنجی شود.
- **مشترک**: `deploy` (در خود سرور `install.sh --update` از GitHub + snapshot/rollback)، `status`, `version`, `logs`.
- **iran**: `ls`, `doctor`, `tune`, `regen`, `restart`, `paths`, `set_config{key,value}`, `backup`, `enable`, `hub_status`؛ transport: `kcp_*`, `plain_*`, `noise_*`, `backhaul_*`, `frp_*`, `gre_*`, `direct_*`؛ دامنه/TLS: `tls_info`, `tls_certs`, `tls_cert`, `domain_*`؛ game/SNI: `game_ls|add|rm|show|cert`؛ نود: `add_node`, `rm_node`, `edit_node`, `rename_node`, `rotate_node`, `show_node`؛ ریورس‌پروکسی غیرتونلی: `proxy_ls|add|rm`.
  - `game_cert` گواهی Let's Encrypt می‌گیرد و خروجی شامل **کلید خصوصی** است؛ فقط از هابِ احرازشده استفاده کن و لاگ نگه ندار.
  - `set_config` علاوه‌بر `domain`/`fullchain`/`key`/`nginx-conf`، پورت‌های `fake-port`/`sub-port`/`control-port` و `sub-path`/`hub-path` را هم می‌پذیرد (این پورت‌ها در بخش مستقل **Ports** صفحه‌ی سرور هم قابل ویرایش‌اند).
- **node**: `show`, `ls`, `status`, `logs`, `upstream_ls`, `set_server`, `set_main`, `control_path_*`, `migrate`, `tune`, `apply`, `restart`, `version`؛ سرویس: `add_svc`, `rm_svc`, `add_bh_svc`, `rm_bh_svc`؛ transport: `kcp_*`, `plain_*`, `noise_*`, `backhaul_*`, `frp_*`, `gre_*`؛ upstream: `upstream_add|add_svc|rm|rm_svc|kcp_*|plain_*|noise_*|ws|apply|restart|logs|status`؛ watchdog/adaptive: `watchdog_*`, `adaptive_*`.
- کشف: `GET /api/servers/<iran>/discover` → لیست نودهای تعریف‌شده در state آن ایران.

UI هنگام باز شدن، وضعیت همه‌ی سرورها را خودکار بارگذاری می‌کند. همه‌ی ورودی‌ها با regex سخت اعتبارسنجی می‌شوند (ضد تزریق).

## مدل امنیتی
- هاب هرگز رشته‌ی خام اجرا نمی‌کند: allow-list action + اعتبارسنجی regex + argv لیستی؛ روی SSH به‌صورت shell-safe (shlex) و روی Agent به‌صورت آرایه‌ی JSON به `/api/exec`.
- `WRITE_ACTIONS` actionهای نوشتاری را علامت می‌زند؛ همان‌ها + `deploy`/`provision`/`config_save` در audit log (`/etc/ratholehub/audit.log`، append-only) ثبت می‌شوند.
- روی `127.0.0.1` می‌شنود؛ ورود مدیر محدود به ۵ تلاش ناموفق در ۵ دقیقه برای هر IP؛ کوکی نشست = `hmac(api_token, expiry)` با اعتبار ۲۴ ساعت.
- `deploy_to_server` روی خود سرور آخرین `install.sh` را از GitHub (با حلقه‌ی mirror ghproxy) می‌گیرد؛ فقط `gh_repo` (اعتبارسنجی `RE_SLUG`) و `update_channel` (`stable|beta`) داخل دستور ثابت `bash -c` جای‌گذاری می‌شوند.

## وضعیت
پیاده‌سازی‌شده: مدیریت inventory با دو مسیر SSH و REST Agent، وضعیت زنده، actionهای امن با whitelist، مدیریت laneهای rathole/Backhaul/FRP/GRE، افزودن/حذف نود و سرویس، کنترل سرویس‌ها (حامل/پروتکل، تست سلامت، VLESS، مدیریت peer، حذف دوطرفه)، routing graph/table/console فقط‌خواندنی، جمع‌آوری log، آپدیت تک‌سرور/همه و badge نسخه.
