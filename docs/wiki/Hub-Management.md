# مدیریت مرکزی با پنل وب Hub

**RatholeHub** یک پنل وب Python 3 stdlib (بدون pip و بدون build فرانت‌اند) است که مدیریت چندین سرور ایران و نود خارج را متمرکز می‌کند. backend در `hub.py`/`hubcmds.py` و UI در پوشه‌ی `ui/` قرار دارد. هاب می‌تواند هر سرور را به دو روش کنترل کند:

| روش اتصال | `transport` | پیش‌نیاز | توضیح |
|-----------|-------------|----------|-------|
| **SSH** | `ssh` | کلید SSH هاب در `authorized_keys` سرور | روش سنتی؛ هر دستور به‌صورت argv از طریق SSH اجرا می‌شود. |
| **REST Agent** | `api` | سرویس `rathole-agent.service` روی سرور + API URL/توکن | بدون SSH؛ هاب درخواست را به `POST <api_url>/api/exec` می‌فرستد. |

> در نسخه‌ی **v2.0.2** صفحه‌ی «بورد سیم‌کشی» (`#/wiring`) حذف شده است. لینک قدیمی `#/wiring` بی‌صدا به داشبورد برمی‌گردد. جای آن، **کنترل‌های سرویس** در ردیف هر سرویس (صفحه‌ی ایران و نود) قرار گرفته است.

![معماری هاب](https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/docs/assets/hub-architecture.svg)

![کنترل‌های سرویس — مودال «حامل و پروتکل» روی یک سرویس](https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/docs/assets/screenshots/service-controls.png)

![نقشهٔ مسیرها — نمای توپولوژی فقط‌خواندنی](https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/docs/assets/screenshots/routing-map.png)

---

## نصب

```bash
# روش پیشنهادی — از طریق ratholectl روی سرور ایران:
sudo ratholectl hub on [port]
# اگر hub نصب نشده باشد، install-hub.sh را خودکار (با HUB_PORT داده‌شده) اجرا می‌کند
# و رمز مدیر را به‌صورت تعاملی می‌پرسد. پیش‌فرض پورت: 8088

# یا مستقیم:
sudo HUB_PORT=8088 bash rathole-manager/ratholehub/install-hub.sh
```

> `install.sh` خودش پرچم `--hub` ندارد (فقط `--release`/`--token`/`--beta` را parse می‌کند و بقیه را به `bootstrap.sh` می‌دهد؛ `--panel`/`--node` از همان مسیر کار می‌کنند). نصب هاب از طریق `ratholectl hub on` یا `install-hub.sh` انجام می‌شود. `install-hub.sh` کانفیگ را فقط اگر وجود نداشته باشد می‌سازد (توکن/رمز موجود پاک نمی‌شود) و کل درخت (`hub.py` + `hubcmds.py` + `ui/`) را نصب می‌کند.

---

## دسترسی به پنل

**امن‌ترین روش (بدون باز کردن پورت):**
```bash
ssh -L 8088:127.0.0.1:8088 root@<ip_server>
# مرورگر: http://localhost:8088
```

**از طریق nginx روی همان دامنه:**
```bash
sudo ratholectl hub on 8088   # → https://<domain>/hub/
```

`ratholectl hub off` فقط مسیر `/hub/` را از nginx برمی‌دارد؛ سرویس روی `127.0.0.1` روشن می‌ماند. وضعیت و هشدار ناهماهنگی پورت: `ratholectl hub status`.

---

## افزودن سرورها

### روش ۱ — SSH (Provision)

در داشبورد، سرور را اضافه کنید و Provision بزنید. هاب یک‌بار با رمز SSH وصل می‌شود، کلید عمومی‌اش را به `authorized_keys` اضافه می‌کند، با `deploy` آخرین نسخه را از GitHub روی سرور نصب/آپدیت می‌کند (`install.sh --update`)، و سرور را در inventory ثبت می‌کند. Provision روی هاب به `sshpass` نیاز دارد (`apt install -y sshpass`) و برای نود، تانل اصلی را هم به سرور ایران وصل می‌کند.

روش دستی:
```bash
ssh-copy-id -i /root/.ssh/id_ed25519.pub root@<server_ip>
# سپس سرور را از طریق POST /api/servers با transport=ssh اضافه کنید
```

### روش ۲ — REST Agent (بدون SSH)

۱. روی سروری که از قبل نصب شده (پنل یا نود) agent را فعال کنید:

```bash
sudo install-agent.sh --role iran --port 8089     # روی سرور ایران
sudo install-agent.sh --role node --port 8089     # روی نود خارج
# یا از داخل CLIها:
sudo ratholectl agent on 8089
sudo ratholenode agent on 8089
```

`ratholeagent.py` و `install-agent.sh` توسط `install-panel.sh`/`install-node.sh` از قبل در `/usr/local/share/rathole/` نصب شده و `install-agent.sh` در `/usr/local/bin/` symlink دارد؛ بنابراین دانلود اضافه لازم نیست. توکن در `/etc/rathole-agent/token` (chmod 600) ذخیره می‌شود؛ `sudo ratholectl agent show` آن را چاپ می‌کند.

۲. در هاب (فرم افزودن سرور → Connection = **Agent REST API**) این‌ها را بدهید:

| فیلد | مقدار |
|------|-------|
| `api_url` | `http://<public_ip>:8089` یا `https://<domain>:8089` |
| `api_token` | همان توکن agent |
| `insecure_ssl` | فقط اگر HTTPS با گواهی self-signed است: این کلید در رکورد inventory (فایل `inventory.json`) ست می‌شود؛ فرم UI فیلد جداگانه‌ای برای آن ندارد. جایگزین ساده‌تر: `RATHOLE_AGENT_INSECURE_SSL=1` در محیط سرویس هاب. |

۳. صحت: `curl -s http://<ip>:8089/api/ping` باید `{ok, role, version, hostname}` برگرداند (این مسیر auth نمی‌خواهد).

**HTTPS:** به `ratholeagent.py` گزینه‌های `--tls-cert`/`--tls-key` بدهید (یا `RATHOLE_AGENT_TLS_CERT`/`RATHOLE_AGENT_TLS_KEY`، یا فایل‌های پیش‌فرض `/etc/rathole-agent/cert.pem` و `key.pem`). گواهی self-signed یا با `insecure_ssl: true` در رکورد inventory همان سرور پذیرفته می‌شود یا با `RATHOLE_AGENT_INSECURE_SSL=1` در محیط هاب (هر دو فقط بررسی گواهی را خاموش می‌کنند؛ ترافیک هنوز TLS است).

> در هاب، badge سرور نشان می‌دهد `⚡ REST API` یا `🔑 SSH` است. اگر agent در دسترس نباشد، وضعیت سرور `no_agent` نمایش داده می‌شود (و نه `no_ssh`).

---

## صفحات رابط کاربری

| صفحه | آدرس | محتوا |
|------|------|-------|
| **داشبورد** | `#/dashboard` | کارت سرورها، grid/list، وضعیت و badge نسخه؛ افزودن/Provision؛ آپدیت همه با progress؛ نوار وضعیت هاب (uptime/load/RAM/دیسک، تعداد متصل، badge پروکسی) |
| **صفحه سرور** | `#/server/<name>` | overview، دامنه/گواهی، پورت/path، carrierها، ingress، سرویس‌های rathole و Backhaul، game، upstreamها، ابزارهای تشخیص و log |
| **مسیریابی / کنسول** | `#/routing` | **فقط‌خواندنی**: نمای گراف/جدول topology و کنسول؛ تغییر مسیر از ردیف سرویس یا کارت حامل انجام می‌شود |
| **فعالیت** | `#/audit` | تاریخچه‌ی عملیات (زمان، کاربر، سرور، action، rc) — ۱۰۰ رکورد آخر |
| **تنظیمات** | `#/settings` | hint listen/token، چرخش API token و تغییر رمز مدیر |

UI برای موبایل/دسکتاپ ریسپانسیو است، تم روشن/تیره و RTL/LTR دارد، وضعیت focus و dialogهای keyboard-accessible را رعایت می‌کند و از `prefers-reduced-motion` پشتیبانی می‌کند. زبان و تم در مرورگر ذخیره می‌شوند. نوار ناوبری چهار بخش دارد: داشبورد، نقشه مسیرها، گزارش فعالیت‌ها، تنظیمات.

---

## کنترل‌های سرویس (نسخه‌ی ۲.۰.۲)

هم در صفحه‌ی ایران و هم در صفحه‌ی نود، هر ردیف سرویس این دکمه‌ها را دارد:

| دکمه | کار |
|------|-----|
| **حامل و پروتکل** | مودال تغییر حامل/پروتکل سرویس: `ws`، `kcp`، `plain`، `noise`، `backhaul`، `frp`، `gre` و ترکیبی `frp+gre`؛ همراه با انتخاب نود خارجی، IP عمومی ایران/نود، آدرس مجازی GRE، ترانسپورت FRP/Backhaul، پروفایل و پورت اختصاصی حامل. |
| **تست سلامت** | `ratholectl doctor` را روی سرور ایران اجرا می‌کند و خروجی را در modal نشان می‌دهد؛ سپس وضعیت تازه خوانده می‌شود. |
| **ساخت کانفیگ VLESS** | از UUID واقعی کاربر Xray، هاست عمومی، پورت، SNI و مسیر WebSocket لینک `vless://` می‌سازد و کپی می‌کند (این ابزار کاربر Xray نمی‌سازد). |
| **مدیریت سمت مقابل** | به صفحه‌ی نودِ سمت مقابل می‌رود؛ اگر نود مشخص نباشد انتخاب می‌شود. |
| **حذف از دو سمت** | پس از تأیید `rm_node` روی ایران و در صورت وجود `rm_svc`/`rm_bh_svc` روی نود را اجرا می‌کند؛ اگر overview نود در دسترس نباشد یا لیست سرویس‌هایش ناقص باشد، از حذف خودداری می‌کند. |

سرویس‌های **Game/SNI**: دکمه‌های «حامل و پروتکل» و «ساخت کانفیگ» پیام `service_game_hint` نشان می‌دهند؛ مدیریت آن‌ها در بخش «سرویس‌های گیمینگ (SNI/443)» صفحه‌ی ایران است.

### برچسب حامل و پروتکل

نام حامل همراه **پروتکل گزارش‌شده از سرور** نمایش داده می‌شود:

| برچسب | معنا |
|-------|------|
| `FRP / TCP` · `FRP / KCP` · `FRP / QUIC` · `FRP / WEBSOCKET` | ترانسپورت گزارش‌شده‌ی هسته‌ی FRP |
| `FRP + GRE / <transport>` | حالت ترکیبی FRP روی GRE — توجه: در پیاده‌سازی فعلی رکورد ایران روی lane `FRP` ثبت می‌شود، پس برچسب گزارش‌شدهٔ سرویس `FRP / <transport>` است |
| `Backhaul / WS` · `Backhaul / WSMUX` · `Backhaul / WSS` · `Backhaul / WSSMUX` | ترانسپورت گزارش‌شده‌ی Backhaul |
| `KCP / UDP · balanced` (یا `lossy` / `aggressive`) | KCP به همراه پروفایل |
| `Noise / TCP` · `WebSocket / TLS` · `WebSocket / TCP` · `GRE / WebSocket` · `SNI / TLS` | برچسب ثابت هر حامل |

علامت `?` یعنی **پروتکل از سرور دریافت نشده است**. این برچسب به‌تنهایی تضمین اتصال نیست؛ برای تأیید از «تست سلامت» استفاده کنید.

### بخش Ports در صفحه سرور

| پورت | قابل ویرایش؟ | توضیح |
|------|-------------|-------|
| `fake-port` | ✅ | سایت فیک (پیش‌فرض ۸۰۸۰) |
| `sub-port` | ✅ | subscription (پیش‌فرض ۲۰۹۶) |
| `control-port` | ✅ | کنترل rathole (پیش‌فرض ۲۳۳۳) |
| `internal` | نمایش | پورت داخلی (پشت SNI) |
| `hub`, `plain`, `noise`, `backhaul`, `direct` | نمایش | پورت هر listener/core (پورت FRP/GRE در کارت همان حامل و وضعیت ایران دیده می‌شود) |

### دکمه‌های کلیدی

- **Badgeهای سرصفحه** — روی صفحه‌ی هر سرور: `doctor ok/fail`، badge حامل اصلی (با پروتکل گزارش‌شده)، `kcp`/`noise`، وضعیت up/down تانل و badge نسخه.
- **«آپدیت همه»** — همه سرورها را ترتیبی آپدیت می‌کند. progress bar زنده: در صف → در حال آپدیت → ✓ نسخه‌ی جدید یا ✗ (rc=N). سروری که خودِ هاب روی آن است ممکن است پس از restart ناقص نشان دهد.
- **Badge نسخه** — سبز = هم‌نسخه با نسخه‌ی bundle خود هاب (`MANAGER_VERSION`)، قرمز `vX → vY` = نیاز به آپدیت.
- **«Set main tunnel»** — نود خارج را به یک سرور ایران ثبت‌شده در هاب وصل می‌کند.
- **«Add to node»** — یک سرویس ایران را به‌عنوان سرویس روی نود خارج ثبت می‌کند (token/inbound واقعی را خودکار دریافت می‌کند).
- **سرویس‌های Backhaul lane** — جدول مستقل مبتنی بر `bh-services.conf`؛ اضافه/حذف سرویس Backhaul، lane رتهول را خاموش نمی‌کند. هنگام افزودن سرویس، lane (`rathole` یا `mux`) پرسیده می‌شود و action مربوطه (`add_svc` یا `add_bh_svc`) اجرا می‌شود.
- **GRE** — کارت حامل GRE در صفحه‌ی ایران (رابط `gre1`، ساب‌نت `10.10.10.0/30`، روشن/خاموش/وضعیت) و فیلدهای `l_gre_remote`/`l_gre_tunnel`/`l_gre_name` در مودال «حامل و پروتکل»؛ برای نودهای REST API، IP عمومی نود/ایران خودکار تشخیص داده می‌شود. `gre_probe` یک action داخلی است که هنگام سوییچ حامل اجرا می‌شود و دکمه‌ی جداگانه در UI ندارد.
- **Log و خروجی** — خروجی بلند در modal قابل کپی باز می‌شود و log جمع‌آوری‌شده به فایل متن دانلود می‌شود.

---

## REST API

همه مسیرها (به‌جز `/api/health` و `/api/login`) با هدر `Authorization: Bearer <API_TOKEN>` یا کوکی نشست از UI کار می‌کنند؛ `/api/health` عمومی است. پشت nginx، مسیرها هم با `/api/...` و هم با `/hub/api/...` در دسترس‌اند.

```
GET    /api/health                              سلامت هاب (بدون auth)
POST   /api/login                              {"password":"..."} → کوکی نشست + توکن
GET    /api/servers                            لیست سرورها
POST   /api/servers                            افزودن سرور (ssh یا api)
PUT    /api/servers/<name>                     ویرایش متادیتا (host/port/کاربر/role/public_ip؛ برای api: api_url/api_token)
DELETE /api/servers/<name>                     حذف سرور از inventory
POST   /api/provision                          نصب خودکار SSH (کلید SSH + deploy + ثبت)
GET    /api/hubstatus                          وضعیت هاب + latest_version
GET    /api/config                             تنظیمات هاب (listen، proxy، ssh_key، hint توکن، insecure)
POST   /api/config                             چرخش API token / تغییر رمز مدیر
GET    /api/audit                              تاریخچه‌ی عملیات
POST   /api/servers/<name>/action              {"action":"...", "args":{...}} → اجرای action مجاز
GET    /api/servers/<name>/status              وضعیت سرور (JSON)
GET    /api/servers/<name>/discover            کشف وضعیت/پورت‌ها
GET    /api/servers/<name>/overview            overview یکپارچه (برای رندر UI)
GET    /api/servers/<name>/details             جزئیات تکمیلی
GET    /api/servers/<name>/frpconnect          اطلاعات اتصال FRP نود
GET    /api/servers/<name>/kcpconnect          کلید/مشخصات KCP
GET    /api/servers/<name>/noiseconnect        pubkey/آدرس Noise
GET    /api/servers/<name>/backhaulconnect     توکن/transport/profile بک‌هال
GET    /api/servers/<name>/mainconnect         SERVER/TLS/control-path تانل اصلی
GET    /api/servers/<iran>/nodeconnect/<node>  token/inbound واقعی نود (برای wire-to-node)
POST   /api/ip-tls/prepare                     آماده‌سازی گواهی IP برای direct-IP/backhaul direct_ip
```

**نمونه:**
```bash
TOKEN=your_token
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8088/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST \
  http://localhost:8088/api/servers/rp01/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"status","args":{}}'
```

---

## مدل امنیتی

هاب هرگز رشته‌ی خام روی سرورها اجرا نمی‌کند:

1. هر درخواست به یک **action مجاز** از allow-list نگاشت می‌شود (`hubcmds.py` → `build_iran_cmd` / `build_node_cmd`)
2. آرگومان‌ها با regex (`RE_NAME`, `RE_IPPORT`, `RE_KEY`, …) اعتبارسنجی می‌شوند
3. دستورات به‌صورت **argv لیستی** اجرا می‌شوند — برای SSH با هر آرگومان جدا، و برای REST Agent به‌صورت `{"cmd":[...]}` — نه string interpolation
4. actionهای تغییردهنده در `WRITE_ACTIONS` علامت‌گذاری شده‌اند و در **audit log** ثبت می‌شوند
5. **سخت‌گیری سمت agent:** فقط بایناری‌های `ratholectl`، `ratholenode`، `bash`، `python3`، `python`، `systemctl`، `journalctl`، `curl`، `jq`، `cat`، `tail`، `ls` مجاز هستند؛ payload بین ۱ بایت و ۱ مگابایت، `timeout` بین ۱ تا ۳۶۰۰ ثانیه، و احراز هویت با مقایسه‌ی constant-time.
6. دکمه «آپدیت» در خودِ سرور آخرین `install.sh` را از GitHub (از طریق mirror ghproxy برای مخزن عمومی) می‌گیرد و با `--update` اجرا می‌کند؛ slug مخزن (`gh_repo`) و کانال آپدیت از config می‌آیند و هر دو regex-validated هستند.

---

## آپدیت گروهی و مخزن خصوصی

- دکمه‌ی update هر سرور = `deploy_to_server`: روی خود سرور `install.sh` آخرین Release را دانلود و `--update` را اجرا می‌کند (snapshot + health-check + rollback خودکار). هاب به bundle محلی وابسته نیست.
- `deploy` برای اتصال **api** هم همان مسیر را طی می‌کند: دستور روی سرور اجرا می‌شود، نه از روی هاب.
- کانال آپدیت از config (`update_channel`: `stable` یا `beta`؛ پیش‌فرض `stable`) خوانده می‌شود. برای سرورهای بتا حتماً `beta` بگذارید تا به نسخه‌ی پایدار قدیمی‌تر downgrade نشوند.
- slug مخزن از config (`gh_repo`، پیش‌فرض `l8PYGIT/RatholeEngine`) و با `RE_SLUG` اعتبارسنجی می‌شود.
- **مخزن خصوصی:** آپدیت گروهی از هاب برای مخزن خصوصی پشتیبانی نمی‌شود (هاب روی سرور به توکن GitHub دسترسی ندارد)؛ روی هر سرور از `tools/update-private.sh` یا `install.sh --token` استفاده کنید. جزئیات: **[Workflow Guides](Workflow-Guides)**.

---

## اجرای محلی (تست و توسعه)

```bash
RATHOLEHUB_MOCK=1 RATHOLEHUB_PORT=8088 python3 rathole-manager/ratholehub/hub.py
# مرورگر: http://127.0.0.1:8088
# RATHOLEHUB_MOCK=1 → SSH/Agent واقعی اجرا نمی‌شود، پاسخ‌های fake برمی‌گردد
```

متغیرهای محیطی: `RATHOLEHUB_HOST`, `RATHOLEHUB_PORT`, `RATHOLEHUB_CONF`, `RATHOLEHUB_INV`, `RATHOLEHUB_MOCK`, `RATHOLE_AGENT_INSECURE_SSL`.
