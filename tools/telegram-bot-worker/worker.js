/**
 * Serverless GitHub -> Telegram Channel Announcer (Cloudflare Worker).
 * Handles GitHub Webhooks (HMAC-SHA256 verified) across ANY repository and
 * posts formatted Telegram HTML cards with inline buttons + OpenGraph banners.
 */

const TG_CAPTION_LIMIT = 1024;
const TG_TEXT_LIMIT = 4096;
const SKIP_MARKER_RE = /<!--\s*no-telegram\s*-->|\[(?:no|skip)-telegram\]/i;
const CODE_OR_MARKER_RE = /(`[^`\n]+`)|(?:<!--\s*no-telegram\s*-->|\[(?:no|skip)-telegram\])/gi;
const SEMVER_RE = /^v?(\d+)\.(\d+)\.(\d+)(?:-(.+))?$/;

function escapeHtml(text = "") {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function mdToTelegramHtml(md = "") {
  const headings = {
    added: "✨ ویژگی‌های جدید",
    changed: "🔄 تغییرات و بهبودها",
    fixed: "🛠 رفع اشکال‌ها",
    security: "🔐 امنیت",
    removed: "🗑 حذف‌شده‌ها",
  };
  const out = [];
  let inFence = false;
  let fenceBuf = [];

  for (const rawLine of String(md).split(/\r?\n/)) {
    const raw =
      inFence || rawLine.trim().startsWith("```")
        ? rawLine
        : rawLine.replace(CODE_OR_MARKER_RE, (_m, code) => code || "");
    const line = raw.trim();
    if (line.startsWith("```")) {
      if (inFence) {
        out.push(`<pre>${escapeHtml(fenceBuf.join("\n"))}</pre>`);
        fenceBuf = [];
        inFence = false;
      } else {
        inFence = true;
        fenceBuf = [];
      }
      continue;
    }
    if (inFence) {
      fenceBuf.push(raw);
      continue;
    }
    if (line.startsWith("> [!")) continue;
    if (line.startsWith(">")) {
      const q = line.replace(/^>+/, "").trim();
      if (q) out.push(`💬 ${formatInline(q)}`);
      continue;
    }
    const hm = line.match(/^#{1,6}\s+(.+)$/);
    if (hm) {
      const label = headings[hm[1].trim().toLowerCase()] || escapeHtml(hm[1].trim());
      if (out.length && out[out.length - 1] !== "") out.push("");
      out.push(`<b>${label}</b>`);
      continue;
    }
    const bm = line.match(/^[-*+]\s+(.+)$/);
    if (bm) {
      out.push(`▸ ${formatInline(bm[1].trim())}`);
      continue;
    }
    if (line === "---") continue;
    out.push(line ? formatInline(raw) : "");
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function formatInline(text) {
  const tokenRe = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(!\[[^\]\n]*\]\([^)\s]+\))|(\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))/g;
  let res = "";
  let pos = 0;
  for (const m of text.matchAll(tokenRe)) {
    const idx = m.index ?? 0;
    if (idx > pos) res += escapeHtml(text.slice(pos, idx));
    const tok = m[0];
    if (m[1]) {
      res += `<code>${escapeHtml(tok.slice(1, -1))}</code>`;
    } else if (m[2]) {
      res += `<b>${escapeHtml(tok.slice(2, -2))}</b>`;
    } else if (m[4]) {
      const split = tok.indexOf("](");
      const label = tok.slice(1, split);
      const url = tok.slice(split + 2, -1);
      res += `<a href="${escapeHtml(url)}">${escapeHtml(label)}</a>`;
    }
    pos = idx + tok.length;
  }
  if (pos < text.length) res += escapeHtml(text.slice(pos));
  return res;
}

function truncateHtmlSafe(htmlText, maxLen) {
  if (htmlText.length <= maxLen) return htmlText;
  let cut = htmlText.slice(0, Math.max(0, maxLen - 48));
  const nl = cut.lastIndexOf("\n");
  if (nl > cut.length / 2) cut = cut.slice(0, nl);
  cut = cut.replace(/<[^>]*$/, "").replace(/&[A-Za-z0-9#]*$/, "").trimEnd();
  const stack = [];
  for (const m of cut.matchAll(/<(\/?)([a-zA-Z]+)(?:\s+[^>]*)?>/g)) {
    const tag = m[2].toLowerCase();
    if (m[1] !== "/") stack.push(tag);
    else if (stack.length && stack[stack.length - 1] === tag) stack.pop();
  }
  const closeTags = stack.reverse().map((t) => `</${t}>`).join("");
  return `${cut}${closeTags}\n<i>… ادامه در گیتهاب</i>`;
}

async function verifySignature(secret, rawBody, headerSig) {
  if (!secret || !headerSig || !headerSig.startsWith("sha256=")) return false;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, rawBody);
  const expected =
    "sha256=" +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  if (expected.length !== headerSig.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ headerSig.charCodeAt(i);
  }
  return diff === 0;
}

async function tgCall(token, method, payload) {
  const resp = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  });
  return resp.json();
}

function repoHashTag(fullName = "") {
  const short = fullName.includes("/") ? fullName.split("/")[1] : fullName;
  const clean = short.replace(/[^A-Za-z0-9_]/g, "");
  return clean ? `#${clean}` : "#GitHub";
}

async function urlExistsImage(url) {
  try {
    const resp = await fetch(url, {
      method: "HEAD",
      headers: { "User-Agent": "github-telegram-announcer" },
      signal: AbortSignal.timeout(4000),
    });
    if (!resp.ok) return false;
    const ctype = (resp.headers.get("content-type") || "").toLowerCase();
    return ctype.startsWith("image/") && !ctype.includes("svg");
  } catch {
    return false;
  }
}

async function urlExists(url) {
  try {
    const resp = await fetch(url, {
      method: "HEAD",
      headers: { "User-Agent": "github-telegram-announcer" },
      signal: AbortSignal.timeout(4000),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

async function resolveReleaseMeta(payload) {
  const repo = payload.repository || {};
  const rel = payload.release || {};
  const fullName = repo.full_name || "unknown/repo";
  const defaultBranch = repo.default_branch || "main";
  const tag = rel.tag_name || "v0.0.0";
  const rawBase = `https://raw.githubusercontent.com/${fullName}/${encodeURIComponent(defaultBranch)}`;
  const customBanner = `${rawBase}/docs/assets/social-preview.png`;
  const altBanner = `${rawBase}/assets/social-preview.png`;
  const changelogUrl = `${rawBase}/CHANGELOG.md`;

  const [hasCustom, hasAlt, hasChangelog] = await Promise.all([
    urlExistsImage(customBanner),
    urlExistsImage(altBanner),
    urlExists(changelogUrl),
  ]);

  const qTag = encodeURIComponent(tag);
  const bannerUrl = hasCustom
    ? `${customBanner}?v=${qTag}`
    : hasAlt
      ? `${altBanner}?v=${qTag}`
      : `https://opengraph.githubassets.com/${qTag}/${fullName}`;

  return { bannerUrl, hasChangelog, defaultBranch };
}

function formatRelease(payload, env, meta = {}) {
  const rel = payload.release || {};
  const repo = payload.repository || {};
  const fullName = repo.full_name || "unknown/repo";
  const repoUrl = repo.html_url || `https://github.com/${fullName}`;
  const defaultBranch = meta.defaultBranch || repo.default_branch || "main";
  const tag = rel.tag_name || "v0.0.0";
  const badge = rel.prerelease ? "🧪 نسخهٔ آزمایشی (Pre-release)" : "🚀 انتشار نسخهٔ پایدار";
  const title = escapeHtml(rel.name || `${repo.name || fullName} ${tag}`);
  const notes = mdToTelegramHtml(rel.body || "") || (repo.description ? escapeHtml(repo.description) : "");
  const channel = env.CHANNEL_HANDLE ? `📢 ${escapeHtml(env.CHANNEL_HANDLE)}  ·  ` : "";
  const footer = `${channel}${repoHashTag(fullName)} #Release`;

  const head = [
    `<b>${badge}</b>`,
    `📦 <b>${title}</b>  ·  <code>${escapeHtml(tag)}</code>`,
    `🗂 مخزن: <a href="${escapeHtml(repoUrl)}">${escapeHtml(fullName)}</a>`,
  ].join("\n");

  const fullBody = notes ? `${head}\n\n${notes}\n\n${footer}` : `${head}\n\n${footer}`;
  const bannerUrl = meta.bannerUrl || `https://opengraph.githubassets.com/${encodeURIComponent(tag)}/${fullName}`;
  const homepageRaw = String(repo.homepage || "").trim();
  const homepage = /^https?:\/\//i.test(homepageRaw) ? homepageRaw : "";
  const secondBtn = meta.hasChangelog
    ? { text: "📖 تغییرات", url: `${repoUrl}/blob/${encodeURIComponent(defaultBranch)}/CHANGELOG.md` }
    : { text: "📋 همهٔ ریلیزها", url: `${repoUrl}/releases` };
  const row2 = homepage
    ? [
        { text: "🌐 وب‌سایت", url: homepage },
        { text: "⭐ گیتهاب", url: repoUrl },
      ]
    : [{ text: "⭐ گیتهاب", url: repoUrl }];
  const markup = {
    inline_keyboard: [
      [
        { text: "⬇️ دانلود ریلیز", url: rel.html_url || `${repoUrl}/releases/tag/${tag}` },
        secondBtn,
      ],
      row2,
    ],
  };
  return { fullBody, bannerUrl, markup };
}

function formatPush(payload, env) {
  const repo = payload.repository || {};
  const fullName = repo.full_name || "unknown/repo";
  const repoUrl = repo.html_url || `https://github.com/${fullName}`;
  const branch = (payload.ref || "").replace(/^refs\/heads\//, "");
  const commits = Array.isArray(payload.commits) ? payload.commits : [];
  const channel = env.CHANNEL_HANDLE ? `📢 ${escapeHtml(env.CHANNEL_HANDLE)}  ·  ` : "";

  const lines = [
    `🔄 <b>به‌روزرسانی در ${escapeHtml(fullName)}</b>`,
    `🌿 شاخه: <code>${escapeHtml(branch)}</code>  ·  تعداد کامیت: <b>${commits.length}</b>`,
    "",
  ];
  for (const c of commits.slice(0, 6)) {
    const sha = escapeHtml((c.id || "").slice(0, 7));
    const msg = escapeHtml((c.message || "").split("\n")[0].slice(0, 90));
    lines.push(`▸ <code>${sha}</code> ${msg}`);
  }
  if (commits.length > 6) lines.push(`▸ … و ${commits.length - 6} کامیت دیگر`);
  lines.push(`\n${channel}${repoHashTag(fullName)} #Update`);

  return {
    text: truncateHtmlSafe(lines.join("\n"), TG_TEXT_LIMIT),
    markup: {
      inline_keyboard: [
        [
          ...(payload.compare ? [{ text: "🔍 تغییرات", url: payload.compare }] : []),
          { text: "⭐ گیتهاب", url: repoUrl },
        ],
      ],
    },
  };
}

function stripCodeSpans(md = "") {
  return String(md)
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`\n]+`/g, "");
}

function shouldSkipRelease(rel = {}, env = {}) {
  const tag = String(rel.tag_name || "").trim();
  const body = String(rel.body || "");
  if (body && SKIP_MARKER_RE.test(stripCodeSpans(body))) return "opt_out_marker";
  const m = tag.match(SEMVER_RE);
  if (env.SKIP_PRERELEASES === "true" && (Boolean(rel.prerelease) || (m && Boolean(m[4])))) {
    return "prerelease";
  }
  if (env.SKIP_PATCH_RELEASES === "true" && m && Number(m[3]) !== 0) {
    return "patch_release";
  }
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return Response.json({ ok: true, service: "github-telegram-announcer" });
    }
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const rawBody = await request.arrayBuffer();
    const sig = request.headers.get("X-Hub-Signature-256") || "";
    if (!(await verifySignature(env.GITHUB_WEBHOOK_SECRET, rawBody, sig))) {
      return Response.json({ ok: false, error: "invalid_signature" }, { status: 401 });
    }

    const event = request.headers.get("X-GitHub-Event") || "";
    const payload = JSON.parse(new TextDecoder().decode(rawBody));

    if (event === "ping") {
      return Response.json({ ok: true, pong: payload.zen || "ok" });
    }

    if (event === "release" && payload.action === "published") {
      const skipReason = shouldSkipRelease(payload.release || {}, env);
      if (skipReason) {
        return Response.json({ ok: true, skipped: skipReason });
      }
      const meta = await resolveReleaseMeta(payload);
      const { fullBody, bannerUrl, markup } = formatRelease(payload, env, meta);
      const photoRes = await tgCall(env.TELEGRAM_BOT_TOKEN, "sendPhoto", {
        chat_id: env.TELEGRAM_CHAT_ID,
        photo: bannerUrl,
        caption: truncateHtmlSafe(fullBody, TG_CAPTION_LIMIT),
        parse_mode: "HTML",
        reply_markup: markup,
      });
      if (photoRes?.ok) return Response.json({ ok: true, mode: "photo" });

      const msgRes = await tgCall(env.TELEGRAM_BOT_TOKEN, "sendMessage", {
        chat_id: env.TELEGRAM_CHAT_ID,
        text: truncateHtmlSafe(fullBody, TG_TEXT_LIMIT),
        parse_mode: "HTML",
        disable_web_page_preview: true,
        reply_markup: markup,
      });
      return Response.json({ ok: Boolean(msgRes?.ok), mode: "message" });
    }

    if (event === "push" && env.NOTIFY_PUSH === "true") {
      const defBranch = payload.repository?.default_branch || "main";
      if (payload.ref === `refs/heads/${defBranch}` && (payload.commits || []).length > 0) {
        const { text, markup } = formatPush(payload, env);
        const msgRes = await tgCall(env.TELEGRAM_BOT_TOKEN, "sendMessage", {
          chat_id: env.TELEGRAM_CHAT_ID,
          text,
          parse_mode: "HTML",
          disable_web_page_preview: true,
          reply_markup: markup,
        });
        return Response.json({ ok: Boolean(msgRes?.ok), mode: "push" });
      }
    }

    if (event === "repository" && payload.action === "created" && env.NOTIFY_NEW_REPO === "true") {
      const repo = payload.repository || {};
      const msg = [
        `✨ <b>مخزن جدید منتشر شد!</b>`,
        `📦 <a href="${escapeHtml(repo.html_url || "")}">${escapeHtml(repo.full_name || "")}</a>`,
        repo.description ? `\n${escapeHtml(repo.description)}` : "",
      ]
        .filter(Boolean)
        .join("\n");
      const msgRes = await tgCall(env.TELEGRAM_BOT_TOKEN, "sendMessage", {
        chat_id: env.TELEGRAM_CHAT_ID,
        text: msg,
        parse_mode: "HTML",
        reply_markup: { inline_keyboard: [[{ text: "⭐ مشاهده در گیتهاب", url: repo.html_url || "https://github.com" }]] },
      });
      return Response.json({ ok: Boolean(msgRes?.ok), mode: "repository" });
    }

    return Response.json({ ok: true, ignored: event });
  },
};
