#!/usr/bin/env python3
"""Serverless GitHub Release & Update announcer for Telegram channels.

Stdlib-only CLI & library designed for GitHub Actions (`release`, `workflow_call`,
and `workflow_dispatch`). Formats release notes safely as Telegram HTML, pairs
them with an inline keyboard and banner image (with automatic `sendMessage`
fallback), and exits 0 if Telegram secrets are not configured yet.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

DEFAULT_CHANNEL = "@l8PY4NET"
TG_TEXT_LIMIT = 4096
TG_CAPTION_LIMIT = 1024

_INLINE_TOKEN_RE = re.compile(
    r"(`[^`\n]+`)"
    r"|(\*\*[^*\n]+\*\*)"
    r"|(!\[[^\]\n]*\]\([^)\s]+\))"
    r"|(\[[^\]\n]+\]\(https?://[^)\s]+\))"
)
_TAG_RE = re.compile(r"<(/?)([a-zA-Z]+)(?:\s+[^>]*)?>")


def escape_html(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape(text, quote=True)


def extract_changelog_section(changelog_path: str, version: str) -> str:
    """Extract release notes for `## [<version>]` from CHANGELOG.md."""
    if not changelog_path or not os.path.isfile(changelog_path):
        return ""
    ver = version.lstrip("v").strip()
    if not ver:
        return ""
    prefix = f"## [{ver}]"
    capturing = False
    lines: list[str] = []
    with open(changelog_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if line.startswith(prefix):
                capturing = True
                continue
            if capturing:
                if line.startswith("## ") or re.match(r"^\[[^\]]+\]:", line):
                    break
                lines.append(line)
    return "\n".join(lines).strip()


def _format_inline_md(text: str) -> str:
    """Convert inline Markdown spans to sanitized Telegram HTML."""
    out: list[str] = []
    pos = 0
    for m in _INLINE_TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append(escape_html(text[pos : m.start()]))
        tok = m.group(0)
        if m.group(1):
            inner = tok[1:-1]
            out.append(f"<code>{escape_html(inner)}</code>")
        elif m.group(2):
            inner = tok[2:-2]
            out.append(f"<b>{escape_html(inner)}</b>")
        elif m.group(3):
            # Strip markdown image tags inside release notes
            pass
        elif m.group(4):
            split = tok.find("](")
            label = tok[1:split]
            url = tok[split + 2 : -1]
            out.append(f'<a href="{escape_html(url)}">{escape_html(label)}</a>')
        pos = m.end()
    if pos < len(text):
        out.append(escape_html(text[pos:]))
    return "".join(out)


def md_to_telegram_html(md_text: str) -> str:
    """Convert GitHub Release / CHANGELOG Markdown cleanly into Telegram HTML."""
    if not md_text:
        return ""
    heading_icons = {
        "added": "✨ ویژگی‌های جدید",
        "changed": "🔄 تغییرات و بهبودها",
        "fixed": "🛠 رفع اشکال‌ها",
        "security": "🔐 امنیت",
        "removed": "🗑 حذف‌شده‌ها",
        "deprecated": "⚠️ منسوخ‌شده‌ها",
    }
    out_lines: list[str] = []
    in_code_block = False
    code_buf: list[str] = []

    for raw in md_text.splitlines():
        line = raw.rstrip("\r\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                out_lines.append(f"<pre>{escape_html(chr(10).join(code_buf))}</pre>")
                code_buf = []
                in_code_block = False
            else:
                in_code_block = True
                code_buf = []
            continue

        if in_code_block:
            code_buf.append(line)
            continue

        if stripped.startswith("> [!"):
            continue
        if stripped.startswith(">"):
            quote_text = stripped.lstrip(">").strip()
            if quote_text:
                out_lines.append(f"💬 {_format_inline_md(quote_text)}")
            continue

        m_head = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if m_head:
            heading = m_head.group(1).strip()
            mapped = heading_icons.get(heading.lower())
            title = mapped if mapped else escape_html(heading)
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            out_lines.append(f"<b>{title}</b>")
            continue

        m_bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        if m_bullet:
            out_lines.append(f"▸ {_format_inline_md(m_bullet.group(1).strip())}")
            continue

        if stripped == "---":
            continue

        out_lines.append(_format_inline_md(line) if stripped else "")

    if in_code_block and code_buf:
        out_lines.append(f"<pre>{escape_html(chr(10).join(code_buf))}</pre>")

    # Collapse excessive blank lines
    cleaned: list[str] = []
    prev_blank = True
    for ln in out_lines:
        if ln == "":
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(ln)
            prev_blank = False
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned)


def truncate_html_safe(html_text: str, max_len: int) -> str:
    """Truncate Telegram HTML safely without broken entities or unclosed tags."""
    if len(html_text) <= max_len:
        return html_text

    # Reserve generous room for ellipsis + closing tags
    budget = max(0, max_len - 48)
    cut = html_text[:budget]
    last_nl = cut.rfind("\n")
    if last_nl > budget // 2:
        cut = cut[:last_nl]

    # Strip any trailing incomplete tag or entity
    cut = re.sub(r"<[^>]*$", "", cut)
    cut = re.sub(r"&[A-Za-z0-9#]*$", "", cut)
    cut = cut.rstrip()

    stack: list[str] = []
    for m in _TAG_RE.finditer(cut):
        closing = m.group(1) == "/"
        tag = m.group(2).lower()
        if not closing:
            stack.append(tag)
        elif stack and stack[-1] == tag:
            stack.pop()

    suffix = "".join(f"</{t}>" for t in reversed(stack)) + "\n<i>… ادامه در صفحهٔ ریلیز</i>"
    res = cut + suffix
    if len(res) > max_len:
        # Fallback harder trim keeping tags balanced
        over = len(res) - max_len
        trim_cut = cut[: max(0, len(cut) - over - 8)]
        trim_cut = re.sub(r"<[^>]*$", "", trim_cut)
        trim_cut = re.sub(r"&[A-Za-z0-9#]*$", "", trim_cut).rstrip()
        stack = []
        for m in _TAG_RE.finditer(trim_cut):
            closing = m.group(1) == "/"
            tag = m.group(2).lower()
            if not closing:
                stack.append(tag)
            elif stack and stack[-1] == tag:
                stack.pop()
        res = trim_cut + "".join(f"</{t}>" for t in reversed(stack)) + "\n…"
    return res


def _repo_short_tag(repo: str) -> str:
    short = repo.split("/")[-1] if "/" in repo else repo
    safe = re.sub(r"[^A-Za-z0-9_]", "", short)
    return f"#{safe}" if safe else "#GitHub"


def build_release_payload(
    *,
    repo: str,
    tag: str,
    title: str = "",
    body_md: str = "",
    release_url: str = "",
    docs_url: str = "",
    install_cmd: str = "",
    channel: str = DEFAULT_CHANNEL,
    prerelease: bool = False,
    caption_limit: int = TG_TEXT_LIMIT,
) -> tuple[str, dict]:
    """Build styled Telegram HTML caption/text and inline keyboard markup."""
    rel_url = release_url or f"https://github.com/{repo}/releases/tag/{tag}"
    repo_url = f"https://github.com/{repo}"
    changelog_url = f"{repo_url}/blob/main/CHANGELOG.md"

    badge = "🧪 نسخهٔ آزمایشی (Pre-release)" if prerelease else "🚀 انتشار نسخهٔ پایدار"
    header_title = escape_html(title or f"{repo.split('/')[-1]} {tag}")

    header_parts = [
        f"<b>{badge}</b>",
        f"📦 <b>{header_title}</b>  ·  <code>{escape_html(tag)}</code>",
        f"🗂 مخزن: <a href=\"{escape_html(repo_url)}\">{escape_html(repo)}</a>",
    ]
    if install_cmd:
        header_parts.append(f"\n⚡ <b>نصب / آپدیت سریع:</b>\n<pre>{escape_html(install_cmd)}</pre>")

    notes_html = md_to_telegram_html(body_md)
    footer_tags = f"{_repo_short_tag(repo)} #Release #{escape_html(re.sub(r'[^A-Za-z0-9_]', '_', tag))}"
    if channel:
        footer_tags = f"📢 {escape_html(channel)}  ·  {footer_tags}"

    header = "\n".join(header_parts)
    if notes_html:
        full_body = f"{header}\n\n{notes_html}\n\n{footer_tags}"
    else:
        full_body = f"{header}\n\n{footer_tags}"

    text = truncate_html_safe(full_body, caption_limit)

    row1 = [
        {"text": "⬇️ دانلود ریلیز", "url": rel_url},
        {"text": "📖 تغییرات", "url": changelog_url},
    ]
    row2 = []
    if docs_url:
        row2.append({"text": "📚 مستندات", "url": docs_url})
    row2.append({"text": "⭐ گیتهاب", "url": repo_url})

    keyboard = {"inline_keyboard": [row1, row2]}
    return text, keyboard


def build_push_payload(
    *,
    repo: str,
    ref: str,
    commits: list[dict],
    compare_url: str = "",
    channel: str = DEFAULT_CHANNEL,
) -> tuple[str, dict]:
    """Build compact Telegram HTML message for branch pushes."""
    branch = ref.removeprefix("refs/heads/")
    repo_url = f"https://github.com/{repo}"
    lines = [
        f"🔄 <b>به‌روزرسانی جدید در {escape_html(repo)}</b>",
        f"🌿 شاخه: <code>{escape_html(branch)}</code>  ·  تعداد کامیت: <b>{len(commits)}</b>",
        "",
    ]
    for c in commits[:6]:
        sha = escape_html((c.get("id") or "")[:7])
        msg = escape_html((c.get("message") or "").splitlines()[0][:90])
        author = escape_html((c.get("author") or {}).get("name", ""))
        lines.append(f"▸ <code>{sha}</code> {msg}" + (f" <i>({author})</i>" if author else ""))
    if len(commits) > 6:
        lines.append(f"▸ … و {len(commits) - 6} کامیت دیگر")

    footer = f"{_repo_short_tag(repo)} #Update"
    if channel:
        footer = f"📢 {escape_html(channel)}  ·  {footer}"
    lines.append(f"\n{footer}")

    text = truncate_html_safe("\n".join(lines), TG_TEXT_LIMIT)
    buttons = []
    if compare_url:
        buttons.append({"text": "🔍 مشاهدهٔ تغییرات", "url": compare_url})
    buttons.append({"text": "⭐ گیتهاب", "url": repo_url})
    return text, {"inline_keyboard": [buttons]}


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_multipart(url: str, fields: dict[str, str], file_field: str, file_path: str) -> dict:
    boundary = f"----RHNotify{uuid.uuid4().hex}"
    body = bytearray()
    for name, val in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(val.encode("utf-8"))
        body.extend(b"\r\n")

    mime, _ = mimetypes.guess_type(file_path)
    mime = mime or "application/octet-stream"
    fname = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        raw_bytes = fh.read()
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{fname}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
    )
    body.extend(raw_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_telegram(
    *,
    token: str,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    photo_path: str | None = None,
    photo_url: str | None = None,
    poster_caption: str | None = None,
) -> dict | None:
    """Send Telegram announcement via sendPhoto (with banner) and fallback to sendMessage.

    Returns API JSON response, or None when secrets are missing (graceful skip).
    """
    if not token or not chat_id:
        print(
            "[telegram_notify] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set; skipping notification."
        )
        return None

    base = f"https://api.telegram.org/bot{token}"
    markup_json = json.dumps(reply_markup, ensure_ascii=False) if reply_markup else ""

    has_photo = bool((photo_path and os.path.isfile(photo_path)) or photo_url)
    if has_photo:
        caption_src = poster_caption if (poster_caption is not None) else text
        caption = truncate_html_safe(caption_src, TG_CAPTION_LIMIT)
        try:
            if photo_path and os.path.isfile(photo_path):
                fields = {
                    "chat_id": str(chat_id),
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                if markup_json:
                    fields["reply_markup"] = markup_json
                res = _post_multipart(f"{base}/sendPhoto", fields, "photo", photo_path)
            else:
                payload: dict = {
                    "chat_id": chat_id,
                    "photo": photo_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                res = _post_json(f"{base}/sendPhoto", payload)
            if res.get("ok"):
                return res
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
            print(f"[telegram_notify] sendPhoto failed ({exc}); falling back to sendMessage.", file=sys.stderr)

    msg_payload: dict = {
        "chat_id": chat_id,
        "text": truncate_html_safe(text, TG_TEXT_LIMIT),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        msg_payload["reply_markup"] = reply_markup
    return _post_json(f"{base}/sendMessage", msg_payload)


def _load_event(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Send formatted GitHub release/update cards to Telegram.")
    ap.add_argument("--tag", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file", default="")
    ap.add_argument("--changelog-file", default="CHANGELOG.md")
    ap.add_argument("--release-url", default="")
    ap.add_argument("--docs-url", default="")
    ap.add_argument("--banner", default="")
    ap.add_argument("--banner-url", default="")
    ap.add_argument("--install-cmd", default="")
    ap.add_argument("--channel", default=os.environ.get("TELEGRAM_CHANNEL", DEFAULT_CHANNEL))
    ap.add_argument("--prerelease", action="store_true")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "l8PYGIT/RatholeEngine"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = _load_event(os.environ.get("GITHUB_EVENT_PATH", ""))

    body_md = args.body
    if not body_md and args.body_file and os.path.isfile(args.body_file):
        with open(args.body_file, "r", encoding="utf-8") as fh:
            body_md = fh.read()

    if event_name == "push" and not args.tag and "commits" in event:
        text, markup = build_push_payload(
            repo=args.repo,
            ref=event.get("ref", "refs/heads/main"),
            commits=event.get("commits", []),
            compare_url=event.get("compare", ""),
            channel=args.channel,
        )
        photo_path = None
        photo_url = None
        poster_caption = None
    else:
        rel = event.get("release", {}) if isinstance(event.get("release"), dict) else {}
        tag = args.tag or rel.get("tag_name") or os.environ.get("GITHUB_REF_NAME", "v0.0.0")
        title = args.title or rel.get("name") or f"{args.repo.split('/')[-1]} {tag}"
        if not body_md:
            body_md = rel.get("body") or extract_changelog_section(args.changelog_file, tag)
        release_url = args.release_url or rel.get("html_url") or ""
        prerelease = bool(args.prerelease or rel.get("prerelease") or any(k in tag for k in ("-beta", "-rc", "-alpha")))

        # Prefer sending full caption with banner when under Telegram's 1024-char sendPhoto cap
        full_text, markup = build_release_payload(
            repo=args.repo,
            tag=tag,
            title=title,
            body_md=body_md,
            release_url=release_url,
            docs_url=args.docs_url,
            install_cmd=args.install_cmd,
            channel=args.channel,
            prerelease=prerelease,
            caption_limit=TG_TEXT_LIMIT,
        )
        banner_exists = bool((args.banner and os.path.isfile(args.banner)) or args.banner_url)
        if banner_exists:
            photo_caption, _ = build_release_payload(
                repo=args.repo,
                tag=tag,
                title=title,
                body_md=body_md,
                release_url=release_url,
                docs_url=args.docs_url,
                install_cmd=args.install_cmd,
                channel=args.channel,
                prerelease=prerelease,
                caption_limit=TG_CAPTION_LIMIT,
            )
            text = full_text
            poster_caption = photo_caption
            photo_path = args.banner if (args.banner and os.path.isfile(args.banner)) else None
            photo_url = args.banner_url or None
        else:
            text = full_text
            poster_caption = None
            photo_path = None
            photo_url = None

    if args.dry_run:
        print(text)
        print("--- REPLY_MARKUP ---")
        print(json.dumps(markup, ensure_ascii=False, indent=2))
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    try:
        res = send_telegram(
            token=token,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            photo_path=photo_path,
            photo_url=photo_url,
            poster_caption=poster_caption,
        )
        if res is not None:
            print(f"[telegram_notify] sent ok={res.get('ok')}")
        return 0
    except Exception as exc:
        print(f"[telegram_notify] failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
