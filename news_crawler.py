#!/usr/bin/env python3
"""抓取公开新闻网页的可读正文，供 Hermes Weather 热点面板使用。

仅抓取用户主动点击的公开 URL；不绕过登录、验证码或 robots 限制。
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 2_500_000
MAX_CHARS = 24_000
BLOCKED_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}
CONTENT_TAGS = {"article", "main", "p", "h1", "h2", "h3", "blockquote"}


def clean_text(value: str) -> str:
    return re.sub(r"\\s+", " ", html.unescape(value or "")).strip()


class ArticleExtractor(HTMLParser):
    """Small dependency-free extractor that favors article/main semantic markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.blocks: list[str] = []
        self._tag_stack: list[str] = []
        self._text: list[str] = []
        self._in_title = False
        self._blocked = 0
        self._in_content = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        self._tag_stack.append(tag)
        if tag in BLOCKED_TAGS:
            self._blocked += 1
        if tag == "title":
            self._in_title = True
        if tag in {"article", "main"}:
            self._in_content = True
        if tag == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            if key in {"og:title", "twitter:title", "description", "og:description"}:
                self.meta[key] = clean_text(attrs_dict.get("content", ""))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"article", "main"}:
            self._in_content = False
        if tag in BLOCKED_TAGS and self._blocked:
            self._blocked -= 1
        if tag in CONTENT_TAGS and self._text and not self._blocked:
            text = clean_text("".join(self._text))
            if len(text) >= 2 and (self._in_content or tag in {"p", "h1"}):
                if not self.blocks or self.blocks[-1] != text:
                    self.blocks.append(text)
            self._text.clear()
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._blocked:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._tag_stack and self._tag_stack[-1] in CONTENT_TAGS:
            self._text.append(data)

    def result(self, url: str) -> dict[str, str]:
        title = self.meta.get("og:title") or self.meta.get("twitter:title") or clean_text("".join(self.title_parts))
        if not title and self.blocks:
            title = self.blocks[0]
        description = self.meta.get("og:description") or self.meta.get("description") or ""
        content = "\n\n".join(self.blocks)
        if not content:
            content = description or "该页面未提供可提取的正文，请打开原文查看。"
        return {"url": url, "title": title[:300], "description": description[:800], "content": content[:MAX_CHARS]}


def _decode_body(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=\\s*([\\w-]+)", content_type, re.I)
    encodings = [match.group(1)] if match else []
    encodings += ["utf-8", "gb18030", "latin-1"]
    for encoding in encodings:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def fetch_article(url: str, timeout: int = 15) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("只允许抓取 http/https 新闻网址")
    if parsed.hostname and parsed.hostname.lower().endswith("bilibili.com"):
        return fetch_bilibili_video(url, timeout)
    request = Request(url, headers={"User-Agent": "HermesWeatherNewsCrawler/1.0", "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("新闻页面超过 2.5 MB，已停止抓取")
        source = _decode_body(body, response.headers.get("Content-Type", ""))
    parser = ArticleExtractor()
    parser.feed(source)
    parser.close()
    return parser.result(url)


def _strip_bili_markup(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", "", html.unescape(value or "")))


_WBI_MIXIN_TABLE = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]
_WBI_CACHE: tuple[float, str] | None = None


def _bili_json(url: str, timeout: int) -> dict:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 HermesWeatherNewsCrawler/1.2", "Referer": "https://search.bilibili.com/", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(MAX_BYTES).decode("utf-8", "replace"))


def _bili_wbi_search(keyword: str, timeout: int) -> dict:
    global _WBI_CACHE
    if _WBI_CACHE and time.time() - _WBI_CACHE[0] < 300:
        mixin = _WBI_CACHE[1]
    else:
        nav = _bili_json("https://api.bilibili.com/x/web-interface/nav", timeout)
        wbi = ((nav.get("data") or {}).get("wbi_img") or {})
        raw_key = "".join((str(wbi.get(name) or "").rsplit("/", 1)[-1].split(".", 1)[0] for name in ("img_url", "sub_url")))
        if len(raw_key) < 64:
            raise ValueError("B 站 WBI 签名密钥不可用")
        mixin = "".join(raw_key[i] for i in _WBI_MIXIN_TABLE)[:32]
        _WBI_CACHE = (time.time(), mixin)
    params = {"search_type": "video", "keyword": keyword, "page": "1", "page_size": "20", "wts": str(int(time.time()))}
    params = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in sorted(params.items())}
    query = urlencode(params)
    params["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return _bili_json("https://api.bilibili.com/x/web-interface/wbi/search/type?" + urlencode(params), timeout)


def fetch_bilibili_video(url: str, timeout: int = 15) -> dict[str, str]:
    """Resolve a Bilibili hot-search URL to its first public video result."""
    parsed = urlparse(url)
    bvid_match = re.search(r"/(BV[0-9A-Za-z]+)", parsed.path)
    bvid = bvid_match.group(1) if bvid_match else ""
    item = None
    if not bvid:
        keyword = parse_qs(parsed.query).get("keyword", [""])[0].strip()
        if not keyword:
            raise ValueError("无法从 B 站链接解析搜索关键词")
        payload = _bili_wbi_search(keyword, timeout)
        results = ((payload.get("data") or {}).get("result") or [])
        if not results:
            raise ValueError("B 站搜索未返回可播放视频")
        item = results[0]
        bvid = str(item.get("bvid") or "")
    if not bvid:
        raise ValueError("B 站视频缺少 BV 号")
    title = _strip_bili_markup(str((item or {}).get("title") or ""))
    canonical = f"https://www.bilibili.com/video/{bvid}"
    if not title:
        title = bvid
    return {
        "kind": "video",
        "platform": "bilibili",
        "url": canonical,
        "title": title[:300],
        "description": _strip_bili_markup(str((item or {}).get("description") or ""))[:800],
        "content": _strip_bili_markup(str((item or {}).get("description") or ""))[:MAX_CHARS],
        "bvid": bvid,
        "author": str((item or {}).get("author") or "").strip(),
        "duration": str((item or {}).get("duration") or "").strip(),
        "cover": str((item or {}).get("pic") or "").strip(),
        "embedUrl": f"https://player.bilibili.com/player.html?isOutside=true&bvid={bvid}&p=1&high_quality=1&danmaku=0&autoplay=0",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取公开新闻网页正文")
    parser.add_argument("url")
    args = parser.parse_args()
    try:
        print(json.dumps(fetch_article(args.url), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
