# نصب دستی با فایل (آفلاین / بدون دسترسی به گیتهاب)

این راهنما برای سرورهایی است که دسترسی مستقیم یا پایدار به GitHub ندارند (فیلتر، دیتاسنتر محدود، یا محیط ایزوله).
فایل‌ها را یک‌بار روی سیستم شخصی یا یک سرور واسط دریافت می‌کنی، به سرور هدف منتقل می‌کنی و با `--local` مستقیماً نصب یا آپدیت را انجام می‌دهی.

!!! info "چرا فایل آمادهٔ Release را برداریم (نه `Source code.zip`)؟"
    فایل `rathole-manager.zip` در صفحهٔ [**GitHub Releases**](https://github.com/l8PYGIT/RatholeEngine/releases/latest) علاوه‌بر اسکریپت‌ها، باینری‌های کامپایل‌شدهٔ هستهٔ پچ‌شدهٔ `rathole` (`x86_64` و `aarch64` با `SHA256SUMS`) و `backhaul` (`uTLS` برای `amd64` و `arm64`) را نیز در دل خود دارد — بنابراین هنگام نصب، هیچ باینری‌ای از GitHub دانلود نمی‌شود.

    در مقابل، دکمهٔ `Source code (zip)` خود گیتهاب باینری‌های کامپایل‌شده را ندارد و نصب هنگام دانلود باینری ممکن است به اینترنت GitHub نیاز پیدا کند.

---

## گام ۱ — تهیهٔ فایل‌های نصب

دو فایل نیاز داری: **`rathole-manager.zip`** (یا `.tar.gz`) و **`bootstrap.sh`**.

=== "دانلود از GitHub Releases (پیشنهادی)"

    از صفحهٔ [آخرین ریلیز RatholeEngine](https://github.com/l8PYGIT/RatholeEngine/releases/latest) (یا تگ مشخصی مثل `v2.1.0`) این دو فایل را دانلود کن:

    - `rathole-manager.zip` *(شامل کد مدیر + هستهٔ `rathole` و `backhaul` با checksum)*
    - `bootstrap.sh` *(نصاب هوشمند محلی)*

    یا با `curl` روی سیستم / سرور واسط بگیر:

    ```bash
    curl -fLO https://github.com/l8PYGIT/RatholeEngine/releases/latest/download/rathole-manager.zip
    curl -fLO https://github.com/l8PYGIT/RatholeEngine/releases/latest/download/bootstrap.sh
    ```

=== "ساخت بسته از سورس محلی (`package.sh`)"

    اگر خودت مخزن را کلون کرده یا تغییر داده‌ای، در لینوکس/مک/WSL بزن:

    ```bash
    bash package.sh
    # خروجی: rathole-manager.zip  (یا rathole-manager.tar.gz اگر zip نصب نباشد)
    ```

    فایل‌های لازم برای انتقال همین **`rathole-manager.zip`** و **`bootstrap.sh`** در ریشهٔ مخزن هستند.

    !!! warning "نکتهٔ مهم برای ویندوز"
        فایل `.zip` را با ابزار `Compress-Archive` ویندوز نساز؛ مسیرها را با `\` ذخیره می‌کند. همیشه از Release یا `bash package.sh` (دارای مسیر `/` و پایان خط `LF`) استفاده کن — با این حال `bootstrap.sh` به‌صورت خودکار backslash و `CRLF` را نیز اصلاح می‌کند.

---

## گام ۲ — انتقال فایل‌ها به سرور

فایل‌ها را روی سرور ایران یا نود خارج داخل پوشه‌ای مثل `/root/` آپلود کن:

=== "Linux / macOS (`scp`)"

    ```bash
    scp rathole-manager.zip bootstrap.sh root@<SERVER_IP>:/root/
    ```

    در صورت تفاوت پورت SSH (مثلاً `2222`):

    ```bash
    scp -P 2222 rathole-manager.zip bootstrap.sh root@<SERVER_IP>:/root/
    ```

=== "Windows (PowerShell / WinSCP)"

    در PowerShell (با OpenSSH داخلی ویندوز):

    ```powershell
    scp .\rathole-manager.zip .\bootstrap.sh root@<SERVER_IP>:/root/
    ```

    یا با ابزار گرافیکی مثل **WinSCP** / **Termius** / **FileZilla** (پروتکل SFTP) هر دو فایل `rathole-manager.zip` و `bootstrap.sh` را در مسیر `/root/` سرور کپی کن.

چک سریع بعد از آپلود روی سرور:

```bash
cd /root && ls -lh rathole-manager.zip bootstrap.sh
```

---

## گام ۳ — اجرا و نصب با فایل محلی

روی سرور به کاربر `root` (یا `sudo`) وارد شو و حالت دلخواه را انتخاب کن.
اگر `rathole-manager.zip` (یا `.tar.gz`) کنار `bootstrap.sh` باشد خودش پیدا می‌شود، اما با پرچم **`--local`** مطمئن‌ترین حالت را داری و هیچ تلاشی برای دانلود انجام نمی‌شود.

=== "تعاملی (ساده‌ترین)"

    ```bash
    cd /root
    sudo bash bootstrap.sh --local ./rathole-manager.zip
    ```

    منوی نقش باز می‌شود:
    - `1` ← نصب **پنل (سرور ایران)** (دامنه و مسیر گواهی را می‌پرسد)
    - `2` ← نصب **نود (سرور خارج)** (`server`، `name`، `token` و `inbound-port` را می‌پرسد)
    - `3` ← **آپدیت** نسخهٔ فعلی با بکاپ و Rollback خودکار
    - `4` ← **فقط آماده‌سازی** در `/opt/rathole-manager` (بدون اجرای نصاب)

=== "پنل ایران (غیرتعاملی)"

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --panel \
      --domain    panel.example.ir \
      --fullchain /root/cert/panel.example.ir/fullchain.pem \
      --key       /root/cert/panel.example.ir/privkey.pem
    ```

    > نیازمند پکیج‌های سیستم (`nginx`، `jq`، `openssl`، `python3` و …) است؛ `install-panel.sh` در صورت وجود مخزن `apt` آن‌ها را نصب می‌کند، اما **هیچ دانلودی از GitHub برای هسته انجام نمی‌دهد**.

=== "نود خارج (غیرتعاملی)"

    ابتدا روی پنل ایران دستور `sudo ratholectl add trk01 2087` را بزن تا توکن را بگیری؛ سپس روی نود خارج (دقت کن آرگومان‌های نود حتماً بعد از `--` می‌آیند):

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --node -- \
      --server panel.example.ir:443 \
      --name trk01 \
      --token <TOKEN> \
      --inbound-port 2087
    ```

    برای افزودن قابلیت اتصال **REST Agent** هم می‌توانید بعد از نصب `sudo install-agent.sh --role node` بزنید.

=== "آپدیت آفلاین (با بکاپ و Rollback)"

    برای ارتقای امن سرورهای از قبل نصب‌شده (ایران، نود یا هاب — نقش‌ها خودکار تشخیص داده می‌شوند):

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --update
    ```

    `update.sh` ابتدا از تنظیمات، کلیدها و سرویس‌ها یک **Snapshot کامل** در `/var/backups/rathole-manager/` می‌گیرد، آپدیت را اعمال و سلامت سرویس‌ها را چک می‌کند و در صورت خطا **خودکار Rollback** می‌کند.

=== "فقط اکسترکت و آماده‌سازی (`--no-run`)"

    اگر فقط می‌خواهی فایل‌ها استخراج، پایان خط‌ها `LF` و دسترسی‌ها تنظیم شوند و خودت بعداً اسکریپت‌ها را با پرچم دلخواه صدا بزنی:

    ```bash
    sudo bash /root/bootstrap.sh --local /root/rathole-manager.zip --no-run
    ```

    فایل‌ها در `/opt/rathole-manager/` آماده می‌شوند و هر زمان خواستی می‌توانی مستقیم اجرا کنی:

    ```bash
    sudo bash /opt/rathole-manager/install-panel.sh --domain panel.example.ir ...
    sudo bash /opt/rathole-manager/install-node.sh --server ...
    ```

=== "نصب مستقیم بدون `bootstrap.sh`"

    اگر فقط فایل `rathole-manager.zip` را آپلود کرده‌ای و `bootstrap.sh` کنار دستت نیست:

    ```bash
    unzip -o /root/rathole-manager.zip -d /tmp/rh
    sudo mkdir -p /opt/rathole-manager
    sudo cp -rf /tmp/rh/rathole-manager/. /opt/rathole-manager/
    find /opt/rathole-manager -type f \( -name '*.sh' -o -name '*.py' -o -name 'ratholectl' -o -name 'ratholenode' \) -exec sed -i 's/\r$//' {} +
    sudo chmod +x /opt/rathole-manager/*.sh /opt/rathole-manager/ratholectl /opt/rathole-manager/ratholenode

    # سپس نقش موردنظر را اجرا کن:
    sudo bash /opt/rathole-manager/install-panel.sh
    # یا روی نود:
    # sudo bash /opt/rathole-manager/install-node.sh --server panel.example.ir:443 --name trk01 --token <TOKEN> --inbound-port 2087
    # یا برای آپدیت:
    # sudo bash /opt/rathole-manager/update.sh
    ```

---

## گام ۴ — انتقال دستی گواهی TLS و بازیابی از بکاپ (اختیاری)

اگر روی سرور ایران امکان اجرای `certbot` نداری یا بکاپ سرور قبلی را منتقل می‌کنی:

=== "انتقال گواهی TLS"

    ```bash
    # روی سیستم مبدا:
    scp fullchain.pem privkey.pem root@<IRAN_IP>:/tmp/

    # روی سرور ایران:
    sudo mkdir -p /root/cert/panel.example.ir
    sudo install -m 644 /tmp/fullchain.pem /root/cert/panel.example.ir/fullchain.pem
    sudo install -m 600 /tmp/privkey.pem   /root/cert/panel.example.ir/privkey.pem
    rm -f /tmp/fullchain.pem /tmp/privkey.pem
    ```

=== "بازیابی از فایل بکاپ (`--restore`)"

    اگر با `ratholectl backup` یا `ratholenode backup` بکاپ گرفته‌ای:

    ```bash
    # بازیابی پنل ایران (state + نودها + توکن‌ها + بازتولید nginx و rathole):
    sudo ratholectl init --restore /root/rathole-panel-backup-YYYYMMDD-HHMMSS.tar.gz

    # یا بازیابی نود خارج:
    sudo bash /opt/rathole-manager/install-node.sh --restore /root/rathole-node-backup-YYYYMMDD-HHMMSS.tar.gz
    ```

---

## گام ۵ — راستی‌آزمایی و عیب‌یابی

بعد از نصب، وضعیت سلامت را چک کن:

```bash
# روی پنل ایران:
sudo ratholectl status
sudo ratholectl doctor

# روی نود خارج:
sudo ratholenode status
sudo ratholenode logs 50
```

| خطا یا علامت | علت رایج | راه‌حل |
|---|---|---|
| `unzip: command not found` یا `install_prereqs` بدون اینترنت | نبود `unzip` روی سیستم بسیار خام | بسته را با پسوند `.tar.gz` ببر (`tar` پیش‌فرض نصب است) یا ابتدا `apt-get install -y unzip` بزن |
| پیام دانلود از GitHub هنگام نصب هسته (`install_rathole`) | استفاده از `Source code (zip)` به‌جای فایل Release | فایل رسمی `rathole-manager.zip` از [**Releases**](https://github.com/l8PYGIT/RatholeEngine/releases/latest) که شامل `core/SHA256SUMS` است را استفاده کن |
| خطای `checksum` یا فرمت فایل نامعتبر | فایل ناقص آپلود شده یا با `Compress-Archive` ویندوز زیپ شده | فایل را با `bash package.sh` بساز یا دوباره دانلود کن؛ اندازه و `unzip -t rathole-manager.zip` را چک کن |
| خطای `\r: command not found` در اجرای مستقیم | باز کردن بدون نرمال‌سازی خط پایان | حتماً نصب را از طریق `bootstrap.sh --local` انجام بده یا دستور `sed -i 's/\r$//'` بخش نصب مستقیم را بزن |

---

**صفحات مرتبط:** [شروع سریع (نصب آنلاین)](quickstart.md) · [نصب دستی گام‌به‌گام اجزا](install-manual.fa.md) · [عیب‌یابی و Rollback](wiki/Troubleshooting.md) · [English version](install-offline.en.md)
