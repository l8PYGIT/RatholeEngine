"""MkDocs hooks that make the docs site self-contained (stdlib only).

Three transformations run on the Markdown of every page before rendering:

1. **GitHub-wiki links.** ``docs/wiki/*.md`` are written for GitHub's wiki,
   where ``[متن](Getting-Started)`` is the canonical link form.  MkDocs cannot
   resolve those, so they are rewritten to ``../Getting-Started/`` — the
   directory-URL form MkDocs emits for ``docs/wiki/Getting-Started.md``.

2. **Links that escape ``docs/``.**  Pages link to repo files such as
   ``../README.md``, ``../LICENSE``, ``../tools/...`` or
   ``../rathole-manager/ratholectl``.  Those files are not part of the site,
   so the links are turned into absolute GitHub URLs
   (``https://github.com/loopy-iri/tunnelplus/blob/main/...``, or
   ``/tree/main/...`` for directories), anchors preserved.

3. **``raw.githubusercontent.com`` assets that point back into ``docs/``.**
   They are replaced with local relative paths so a build never depends on
   raw.githubusercontent.com (often unreachable from inside Iran).

Fenced code blocks and inline code spans are skipped so examples that document
these link forms stay literal.

Wire it up in ``mkdocs.yml``::

    hooks:
      - tools/mkdocs_wiki_links.py
"""

from __future__ import annotations

import os
import posixpath
import re

REPO = "loopy-iri/tunnelplus"
REPO_URL = "https://github.com/" + REPO
RAW_DOCS_PREFIX = "https://raw.githubusercontent.com/" + REPO + "/main/docs/"

# `](target)` without spaces or parentheses; finds nested links too because it
# is not anchored on the opening bracket.
_LINK = re.compile(r"\]\((?P<target>[^()\s]+)\)")
# Opening/closing fence of a fenced code block.
_FENCE = re.compile(r"^\s*(```|~~~)")
# Inline code span: one or more backticks ... same run of backticks.
_INLINE_CODE = re.compile(r"(`+)([^\n]*?)\1")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")
# A line that opens a raw <div> block. Several docs wrap their whole page in
# `<div align="center">` / `<div dir="rtl">` (GitHub renders Markdown inside
# those, Python-Markdown does not). Adding `markdown` turns them into
# md_in_html blocks so the page renders as Markdown instead of raw text.
_BLOCK_DIV = re.compile(r"^(?P<indent>\s*)<div(?P<attrs>[^>]*)>", re.IGNORECASE)
# Raw `<img src="...">` tags: MkDocs does not rewrite attributes of raw HTML
# blocks, so a page-relative asset path has to be fixed here.
_RAW_IMG = re.compile(
    r"(?P<open><img\b[^>]*?\bsrc=\")"
    r"(?P<url>[^\"]+)"
    r"(?P<close>\")",
    re.IGNORECASE,
)

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _split_anchor(target: str) -> tuple[str, str]:
    """Split ``path#anchor`` into its two parts."""
    path, _, anchor = target.partition("#")
    return path, anchor


def _rewrite_raw_asset(target: str, docs_dir: str, page_dir: str) -> str:
    """Point raw.githubusercontent docs assets at the local copy."""
    if not target.startswith(RAW_DOCS_PREFIX):
        return target
    rest = target[len(RAW_DOCS_PREFIX):]
    rest, hash_sep, anchor = rest.partition("#")
    rest, query_sep, query = rest.partition("?")
    if not rest:
        return target
    local = os.path.join(docs_dir, *rest.split("/"))
    if not os.path.isfile(local):
        return target
    rel = posixpath.relpath(rest, page_dir or ".")
    if hash_sep:
        rel += "#" + anchor
    if query_sep:
        rel += "?" + query
    return rel


def _rewrite_wiki_link(target: str, docs_dir: str) -> str:
    """``](Page)`` -> ``](../Page/)`` for pages that live in docs/wiki/."""
    path, anchor = _split_anchor(target)
    if not path or "/" in path or "\\" in path or path.endswith(".md"):
        return target
    if not os.path.isfile(os.path.join(docs_dir, "wiki", path + ".md")):
        return target
    url = "../" + path + "/"
    return url + "#" + anchor if anchor else url


def _rewrite_escaped(target: str, docs_dir: str, repo_root: str, page_dir: str) -> str:
    """Turn relative links that leave docs/ into absolute GitHub URLs."""
    path, anchor = _split_anchor(target)
    if not path:
        return target
    resolved = posixpath.normpath(posixpath.join("docs", page_dir, path))
    if resolved == "docs" or resolved.startswith("docs/"):
        return target  # stays inside the site; MkDocs resolves it
    if resolved.startswith(".."):
        return target  # escapes the repository itself; leave it alone
    fs_path = os.path.join(repo_root, *resolved.split("/"))
    kind = "tree" if resolved.endswith("/") or os.path.isdir(fs_path) else "blob"
    url = f"{REPO_URL}/{kind}/main/{resolved}"
    if anchor:
        url += "#" + anchor
    return url


def _rewrite_target(
    target: str, docs_dir: str, repo_root: str, page_dir: str
) -> str:
    if not target or target.startswith(("#", "/", "//", "data:", "javascript:")):
        return target
    if target.startswith(RAW_DOCS_PREFIX):
        return _rewrite_raw_asset(target, docs_dir, page_dir)
    if _SCHEME.match(target) or target.startswith("mailto:"):
        return target
    if page_dir == "wiki":
        rewritten = _rewrite_wiki_link(target, docs_dir)
        if rewritten is not target:
            return rewritten
    return _rewrite_escaped(target, docs_dir, repo_root, page_dir)


def _url_depth(src_uri: str) -> int:
    """Number of path segments in the built page URL directory."""
    dir_part = posixpath.dirname(src_uri)
    name = posixpath.splitext(posixpath.basename(src_uri))[0]
    segments = dir_part.split("/") if dir_part else []
    if name != "index":
        segments.append(name)
    return len(segments)


def _fix_raw_images(line: str, docs_dir: str, page_dir: str, depth: int) -> str:
    """Prefix raw `<img src="...">` with the page's URL depth."""
    prefix = "../" * depth

    def replace(match: re.Match[str]) -> str:
        url = match.group("url")
        if (
            not url
            or url.startswith(("/", "#", "//", "data:"))
            or _SCHEME.match(url)
        ):
            return match.group(0)
        resolved = posixpath.normpath(posixpath.join(page_dir, url))
        if resolved.startswith(".."):
            return match.group(0)
        if not os.path.isfile(os.path.join(docs_dir, *resolved.split("/"))):
            return match.group(0)
        return match.group("open") + prefix + url + match.group("close")

    return _RAW_IMG.sub(replace, line)


def _enable_md_in_html(line: str) -> str:
    """Add `markdown` to line-leading <div> wrappers so md_in_html sees them."""
    match = _BLOCK_DIV.match(line)
    if not match or "markdown" in match.group("attrs").lower():
        return line
    return (
        match.group("indent")
        + "<div"
        + match.group("attrs").rstrip()
        + " markdown>"
        + line[match.end():]
    )


def _rewrite_line(
    line: str, docs_dir: str, repo_root: str, page_dir: str, depth: int
) -> str:
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return "\x00%d\x00" % (len(spans) - 1)

    masked = _INLINE_CODE.sub(stash, line)

    def replace(match: re.Match[str]) -> str:
        target = match.group("target")
        new_target = _rewrite_target(target, docs_dir, repo_root, page_dir)
        if new_target == target:
            return match.group(0)
        return "](" + new_target + ")"

    masked = _LINK.sub(replace, masked)
    if spans:
        masked = _PLACEHOLDER.sub(lambda m: spans[int(m.group(1))], masked)
    masked = _fix_raw_images(masked, docs_dir, page_dir, depth)
    return _enable_md_in_html(masked)


def on_page_markdown(markdown, page, config, files):
    """MkDocs hook: rewrite per-page Markdown before it is rendered."""
    docs_dir = os.path.abspath(config["docs_dir"])
    repo_root = os.path.dirname(docs_dir)
    src_uri = page.file.src_uri.replace(os.sep, "/")
    page_dir = posixpath.dirname(src_uri)
    depth = _url_depth(src_uri)

    lines: list[str] = []
    in_fence = False
    for line in markdown.splitlines(keepends=True):
        if _FENCE.match(line):
            in_fence = not in_fence
            lines.append(line)
            continue
        if in_fence:
            lines.append(line)
            continue
        lines.append(
            _rewrite_line(line, docs_dir, repo_root, page_dir, depth)
        )
    return "".join(lines)
