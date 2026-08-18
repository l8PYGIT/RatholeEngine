# برنامه اجرای بهبودهای کم‌ریسک

## هدف

کاهش ریسک و تکرار در مسیرهای پرتکرار، بدون شکستن قراردادهای CLI یا بازنویسی بزرگ دو اسکریپت اصلی.

## مراحل

1. جایگزینی `eval` در `ratholectl doctor` با predicateهای صریح و آرایه‌محور.
2. افزودن regression test برای doctor تا تضمین شود command ورودی به shell تفسیر نمی‌شود.
3. اجرای تست‌های موجود مربوط به syntax، hub و generatorها؛ در صورت در دسترس بودن Bash/Linux، اجرای harness کامل.
4. در مرحله بعدی، refactor بزرگ‌تر state mutation و شکستن CLIها به ماژول‌ها به‌صورت migration جداگانه.

## فایل‌های درگیر

- `rathole-manager/ratholectl`
- `tests/test_doctor_no_eval.sh`

## معیار پذیرش

- هیچ `eval`ای برای اجرای command در doctor باقی نماند.
- خروجی و شمارش OK/FAIL doctor حفظ شود.
- تست جدید روی shell metacharacterها fail-safe باشد.
- تغییرات محلی موجود در فایل‌های دیگر دست‌نخورده بمانند.
