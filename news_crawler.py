#!/usr/bin/env python3
"""抓取公开新闻网页的可读正文，供 Hermes Weather 热点面板使用。

仅抓取用户主动点击的公开 URL；不绕过登录、验证码或 robots 限制。
"""
from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import re
import socket
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

MAX_BYTES = 2_500_000
MAX_CHARS = 24_000
BLOCKED_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}
CONTENT_TAGS = {"article", "main", "p", "h1", "h2", "h3", "blockquote"}
TEXT_BLOCK_TAGS = {"p", "h1", "h2", "h3", "blockquote"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
ARTICLE_CLASSES = {"article", "article-content", "article-body", "post-content", "entry-content", "rich-text", "kr-rich-text-wrapper"}
ALLOWED_NEWS_DOMAINS = ("thepaper.cn", "bilibili.com", "qbitai.com", "36kr.com")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


class ArticleExtractor(HTMLParser):
    """Small dependency-free extractor that favors article/main semantic markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.blocks: list[str] = []
        self.images: list[dict[str, str]] = []
        self.content_blocks: list[dict[str, str]] = []
        self._tag_stack: list[str] = []
        self._content_markers: list[bool] = []
        self._content_depth = 0
        self._text: list[str] = []
        self._in_title = False
        self._blocked = 0
        self._in_content = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in TEXT_BLOCK_TAGS and self._text:
            self._flush_text()
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        classes = set(attrs_dict.get("class", "").split())
        content_marker = tag in {"article", "main"} or bool(classes & ARTICLE_CLASSES)
        if tag not in VOID_TAGS:
            self._tag_stack.append(tag)
            self._content_markers.append(content_marker)
            if content_marker:
                self._content_depth += 1
        if tag in BLOCKED_TAGS:
            self._blocked += 1
        if tag == "title":
            self._in_title = True
        self._in_content = self._content_depth > 0
        if tag == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            if key in {"og:title", "twitter:title", "description", "og:description", "og:image", "twitter:image"}:
                self.meta[key] = clean_text(attrs_dict.get("content", ""))
        if tag == "img" and self._in_content and not self._blocked:
            if self._text:
                self._flush_text()
            image_url = attrs_dict.get("data-src") or attrs_dict.get("data-original") or attrs_dict.get("src") or ""
            decorative = any(token.startswith(("avatar", "logo", "icon")) for token in classes) or bool(re.search(r"(?:qrcode|avatar|/themes/.*/head\.)", image_url, re.I))
            if image_url and not image_url.startswith("data:") and not decorative:
                image = {"url": image_url.strip(), "alt": clean_text(attrs_dict.get("alt", ""))[:300]}
                if not any(item["url"] == image["url"] for item in self.images):
                    self.images.append(image)
                    self.content_blocks.append({"type": "image", **image})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def _flush_text(self) -> None:
        text = clean_text("".join(self._text))
        if text and (self._in_content or any(tag in {"p", "h1"} for tag in self._tag_stack)):
            if not self.blocks or self.blocks[-1] != text:
                self.blocks.append(text)
                self.content_blocks.append({"type": "text", "text": text})
        self._text.clear()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in BLOCKED_TAGS and self._blocked:
            self._blocked -= 1
        if tag in CONTENT_TAGS and self._text and not self._blocked:
            self._flush_text()
        if tag not in self._tag_stack:
            return
        index = len(self._tag_stack) - 1 - self._tag_stack[::-1].index(tag)
        for marker in self._content_markers[index:]:
            if marker:
                self._content_depth = max(0, self._content_depth - 1)
        del self._tag_stack[index:]
        del self._content_markers[index:]
        self._in_content = self._content_depth > 0

    def handle_data(self, data: str) -> None:
        if self._blocked:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._in_content and (any(tag in TEXT_BLOCK_TAGS for tag in self._tag_stack) or (self._tag_stack and self._tag_stack[-1] in {"article", "main"})):
            self._text.append(data)

    def result(self, url: str) -> dict:
        title = self.meta.get("og:title") or self.meta.get("twitter:title") or clean_text("".join(self.title_parts))
        if not title and self.blocks:
            title = self.blocks[0]
        description = self.meta.get("og:description") or self.meta.get("description") or ""
        content = "\n\n".join(self.blocks)
        if not content:
            content = description or "该页面未提供可提取的正文，请打开原文查看。"
        cover = self.meta.get("og:image") or self.meta.get("twitter:image") or ""
        images = [{**item, "url": urljoin(url, item["url"])} for item in self.images]
        content_blocks = [{**item, **({"url": urljoin(url, item["url"])} if item.get("type") == "image" else {})} for item in self.content_blocks]
        return {
            "kind": "article",
            "url": url,
            "title": title[:300],
            "description": description[:800],
            "content": content[:MAX_CHARS],
            "cover": urljoin(url, cover) if cover else (images[0]["url"] if images else ""),
            "images": images[:20],
            "contentBlocks": content_blocks[:80],
        }


def _decode_body(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=\s*([\w-]+)", content_type, re.I)
    encodings = [match.group(1)] if match else []
    encodings += ["utf-8", "gb18030", "latin-1"]
    for encoding in encodings:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("只允许抓取 http/https 新闻网址")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("新闻网址域名无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("禁止访问私有或本机网络地址")


def validate_news_url(url: str) -> None:
    validate_public_url(url)
    hostname = (urlparse(url).hostname or "").lower()
    if not any(hostname == domain or hostname.endswith("." + domain) for domain in ALLOWED_NEWS_DOMAINS):
        raise ValueError("不受支持的新闻来源")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


def open_news_url(url: str, headers: dict[str, str], timeout: int, max_redirects: int = 4):
    current = url
    for _ in range(max_redirects + 1):
        validate_news_url(current)
        try:
            return _NO_REDIRECT_OPENER.open(Request(current, headers=headers), timeout=timeout)
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location", "")
            exc.close()
            if not location:
                raise ValueError("新闻网址重定向缺少目标地址")
            current = urljoin(current, location)
    raise ValueError("新闻网址重定向次数过多")


def _find_36kr_detail(value, target_id: str | None = None):
    if isinstance(value, dict):
        if value.get("widgetContent") and (value.get("widgetTitle") or value.get("title")):
            item_id = value.get("itemId") or value.get("item_id") or value.get("id")
            if target_id is None or str(item_id) == target_id:
                return value
        for child in value.values():
            found = _find_36kr_detail(child, target_id)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_36kr_detail(child, target_id)
            if found:
                return found
    return None


def parse_36kr_article_page(page: str, url: str) -> dict:
    canonical_match = re.search(r'<meta[^>]+(?:name|property)=["\']og:url["\'][^>]+content=["\']([^"\']+)', page, re.I)
    if not canonical_match or urlparse(html.unescape(canonical_match.group(1))).path.rstrip("/") != urlparse(url).path.rstrip("/"):
        raise ValueError("36氪正文网址不匹配")
    marker = "window.initialState="
    start = page.find(marker)
    if start < 0:
        raise ValueError("36氪正文数据不可用")
    state, _ = json.JSONDecoder().raw_decode(page[start + len(marker):])
    parsed_path = urlparse(url).path
    id_match = re.search(r"/(?:p|newsflashes)/(\d+)", parsed_path)
    if parsed_path.startswith("/newsflashes/"):
        bucket = state.get("newsflashDetail") if isinstance(state, dict) else None
        detail = bucket.get("detail") if isinstance(bucket, dict) else None
        if not isinstance(detail, dict) or not detail.get("widgetContent") or not detail.get("widgetTitle"):
            detail = None
    else:
        detail = _find_36kr_detail(state, id_match.group(1) if id_match else None)
    if not detail:
        raise ValueError("36氪正文数据不可用")
    parser = ArticleExtractor()
    parser.feed("<article>" + str(detail.get("widgetContent") or "") + "</article>")
    parser.close()
    result = parser.result(url)
    cover_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page, re.I)
    result.update({
        "title": clean_text(str(detail.get("widgetTitle") or detail.get("title") or result["title"]))[:300],
        "description": clean_text(str(detail.get("summary") or detail.get("description") or ""))[:800],
        "cover": html.unescape(cover_match.group(1)) if cover_match else result.get("cover", ""),
        "platform": "36kr",
    })
    return result


def fetch_36kr_article(url: str, timeout: int = 15) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
        "Accept": "text/html,application/xhtml+xml",
    }
    with open_news_url(url, headers, timeout) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("新闻页面超过 2.5 MB，已停止抓取")
        page = _decode_body(body, response.headers.get("Content-Type", ""))
    return parse_36kr_article_page(page, url)


def fetch_article(url: str, timeout: int = 15, allow_private: bool = False) -> dict:
    if not allow_private:
        validate_news_url(url)
    parsed = urlparse(url)
    if parsed.hostname and parsed.hostname.lower().endswith("bilibili.com"):
        return fetch_bilibili_video(url, timeout)
    if parsed.hostname and parsed.hostname.lower().endswith("36kr.com") and re.match(r"/(?:p|newsflashes)/", parsed.path):
        return fetch_36kr_article(url, timeout)
    headers = {"User-Agent": "HermesWeatherNewsCrawler/1.0", "Accept": "text/html,application/xhtml+xml"}
    response_context = urlopen(Request(url, headers=headers), timeout=timeout) if allow_private else open_news_url(url, headers, timeout)
    with response_context as response:
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
