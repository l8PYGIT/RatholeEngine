import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import telegram_notify as tn


class TelegramNotifyTests(unittest.TestCase):
    def test_md_to_telegram_html_sanitizes_and_formats(self):
        md = (
            "### Added\n"
            "- **Apple Glass** with `<dialog>` & `vazirmatn.woff2` [Docs](https://l8pygit.github.io/RatholeEngine/)\n"
            "![ignored](docs/assets/banner-dark.png)\n"
            "### Fixed\n"
            "- Prevent <script>alert(1)</script> in notes\n"
        )
        out = tn.md_to_telegram_html(md)
        self.assertIn("<b>✨ ویژگی‌های جدید</b>", out)
        self.assertIn("<b>🛠 رفع اشکال‌ها</b>", out)
        self.assertIn("<b>Apple Glass</b>", out)
        self.assertIn("<code>&lt;dialog&gt;</code>", out)
        self.assertIn('<a href="https://l8pygit.github.io/RatholeEngine/">Docs</a>', out)
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("![ignored]", out)

    def test_truncate_html_safe_closes_open_tags_within_limit(self):
        long_html = "<b>" + "\n".join(f"▸ خط تست شماره {i} <code>cmd_{i}</code>" for i in range(60)) + "</b>"
        trimmed = tn.truncate_html_safe(long_html, 1024)
        self.assertLessEqual(len(trimmed), 1024)
        # Verify balanced tags
        stack = []
        for m in re.finditer(r"<(/?)([a-zA-Z]+)(?:\s+[^>]*)?>", trimmed):
            closing = m.group(1) == "/"
            tag = m.group(2).lower()
            if not closing:
                stack.append(tag)
            elif stack and stack[-1] == tag:
                stack.pop()
        self.assertEqual(stack, [], f"Unclosed tags left in truncated output: {stack}")

    def test_extract_changelog_section_reads_only_target_version(self):
        sample = (
            "## [Unreleased]\n\n"
            "## [2.1.0] - 2026-11-21\n\n"
            "### Added\n- Feature X\n\n"
            "## [2.0.5] - 2026-11-20\n\n"
            "### Fixed\n- Older fix\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(sample)
            tmp_path = fh.name
        try:
            sec = tn.extract_changelog_section(tmp_path, "v2.1.0")
            self.assertIn("Feature X", sec)
            self.assertNotIn("Older fix", sec)
        finally:
            os.unlink(tmp_path)

    def test_build_release_payload_buttons_and_prerelease(self):
        text, markup = tn.build_release_payload(
            repo="l8PYGIT/RatholeEngine",
            tag="v2.1.0-beta.1",
            title="RatholeEngine v2.1.0-beta.1",
            body_md="### Added\n- **Test** item",
            docs_url="https://l8pygit.github.io/RatholeEngine/",
            install_cmd="curl -fsSL https://example.com/install.sh | sudo bash",
            prerelease=True,
        )
        self.assertIn("Pre-release", text)
        self.assertIn("<code>v2.1.0-beta.1</code>", text)
        self.assertIn("⬇️ دانلود ریلیز", markup["inline_keyboard"][0][0]["text"])
        self.assertEqual(
            markup["inline_keyboard"][1][0]["url"],
            "https://l8pygit.github.io/RatholeEngine/",
        )

    def test_send_telegram_skips_cleanly_without_secrets(self):
        res = tn.send_telegram(token="", chat_id="", text="hello")
        self.assertIsNone(res)

    def test_send_telegram_falls_back_from_photo_error_to_send_message(self):
        class FakeResp:
            def __init__(self, body):
                self._b = json.dumps(body).encode("utf-8")
            def read(self):
                return self._b
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        calls = []
        def fake_urlopen(req, timeout=20):
            calls.append(req.full_url)
            if req.full_url.endswith("/sendPhoto"):
                raise OSError("network glitch on photo upload")
            return FakeResp({"ok": True, "result": {"message_id": 42}})

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = tn.send_telegram(
                token="123:abc",
                chat_id="@l8PY4NET",
                text="<b>Release v2.1.0</b>",
                reply_markup={"inline_keyboard": []},
                photo_url="https://example.com/banner.png",
            )
        self.assertTrue(res["ok"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith("/sendPhoto"))
        self.assertTrue(calls[1].endswith("/sendMessage"))


if __name__ == "__main__":
    unittest.main()
