import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

import news_crawler
from news_crawler import ArticleExtractor, clean_text, fetch_article, fetch_bilibili_video, open_news_url, parse_36kr_article_page, validate_public_url


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = '''<!doctype html><html><head><title>Fallback title</title>
        <meta property="og:title" content="真实新闻标题">
        <meta name="description" content="新闻摘要">
        </head><body><nav>导航</nav><article><h1>真实新闻标题</h1>
        <p>第一段新闻正文。</p><p>第二段新闻正文。</p></article>
        <script>不要采集</script></body></html>'''.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class NewsCrawlerTests(unittest.TestCase):
    def test_extractor_prefers_metadata_and_article_text(self):
        parser = ArticleExtractor()
        parser.feed('<html><head><meta property="og:title" content="标题"></head><body><article><p>正文一</p><p>正文二</p></article></body></html>')
        result = parser.result("https://example.com/news")
        self.assertEqual(result["title"], "标题")
        self.assertIn("正文一", result["content"])
        self.assertIn("正文二", result["content"])
        self.assertNotIn("script", result["content"])

    def test_fetch_article_returns_readable_article_from_http_fixture(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = fetch_article(f"http://127.0.0.1:{server.server_port}/news", allow_private=True)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(result["title"], "真实新闻标题")
        self.assertEqual(result["description"], "新闻摘要")
        self.assertEqual(result["content"].count("新闻正文"), 2)

    def test_public_crawler_rejects_private_and_metadata_destinations(self):
        for url in ("http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data", "http://[::1]/"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "私有或本机"):
                    validate_public_url(url)

    def test_article_crawler_rejects_unapproved_public_hosts(self):
        with self.assertRaisesRegex(ValueError, "不受支持"):
            fetch_article("https://example.com/article")

    def test_redirect_target_is_validated_before_second_network_request(self):
        headers = Message()
        headers["Location"] = "http://127.0.0.1/private"
        redirect = HTTPError("https://www.qbitai.com/post", 302, "Found", headers, None)
        with patch.object(news_crawler._NO_REDIRECT_OPENER, "open", side_effect=redirect) as mocked_open:
            with self.assertRaisesRegex(ValueError, "私有或本机"):
                open_news_url("https://www.qbitai.com/post", {"User-Agent": "test"}, 2)
        self.assertEqual(mocked_open.call_count, 1)

    def test_extractor_returns_article_images_and_cover_with_absolute_urls(self):
        parser = ArticleExtractor()
        parser.feed('''<html><head><meta property="og:image" content="/cover.jpg"></head>
        <body><header><img src="/logo.png"></header><article>
        <p>图文正文</p><img src="/body-a.jpg" alt="配图A">
        <img data-src="https://cdn.example.com/body-b.webp" alt="配图B"></article></body></html>''')
        result = parser.result("https://news.example.com/posts/1")
        self.assertEqual(result["cover"], "https://news.example.com/cover.jpg")
        self.assertEqual(result["images"], [
            {"url": "https://news.example.com/body-a.jpg", "alt": "配图A"},
            {"url": "https://cdn.example.com/body-b.webp", "alt": "配图B"},
        ])
        self.assertNotIn("logo.png", str(result["images"]))

    def test_extractor_recognizes_publisher_article_class_as_content(self):
        parser = ArticleExtractor()
        parser.feed('''<div class="article"><div class="article_info"><img class="avatar avatar-200" src="/author.jpg"></div>
        <h1>科技文章</h1><p>正文内容足够明确。</p>
        <div class="pgc-img"><img src="/ai-chip.webp" alt="AI芯片"></div></div>
        <aside><img src="/recommendation.jpg"></aside>''')
        result = parser.result("https://publisher.example/posts/2")
        self.assertIn("正文内容", result["content"])
        self.assertEqual(result["images"], [{"url": "https://publisher.example/ai-chip.webp", "alt": "AI芯片"}])

    def test_extractor_preserves_inline_text_self_closing_images_and_article_boundary(self):
        parser = ArticleExtractor()
        parser.feed('<article><p>A <strong>B</strong> C</p><img src="/x.webp"/><p>D</p></article><p>OUT</p>')
        result = parser.result("https://publisher.example/posts/3")
        self.assertIn("A B C", result["content"])
        self.assertIn("D", result["content"])
        self.assertNotIn("OUT", result["content"])
        self.assertEqual(result["images"], [{"url": "https://publisher.example/x.webp", "alt": ""}])
        self.assertEqual([block["type"] for block in result["contentBlocks"]], ["text", "image", "text"])

    def test_extractor_closes_unbalanced_paragraphs_at_article_end(self):
        parser = ArticleExtractor()
        parser.feed('<article><p>A<p>B</article><p>OUT</p>')
        result = parser.result("https://publisher.example/posts/4")
        self.assertIn("A", result["content"])
        self.assertIn("B", result["content"])
        self.assertNotIn("OUT", result["content"])

    def test_clean_text_collapses_real_whitespace(self):
        self.assertEqual(clean_text("  a   b\n c  "), "a b c")

    def test_parse_36kr_article_page_extracts_state_body_and_images(self):
        state = {"article": {"detail": {"data": {
            "itemId": 100,
            "widgetTitle": "36氪深度文章",
            "summary": "文章摘要",
            "widgetContent": '<p>第一段正文。</p><img src="https://img.36krcdn.com/body.jpg" alt="正文图">',
        }}}}
        page = '<meta name="og:url" content="https://m.36kr.com/p/100"><meta property="og:image" content="https://img.36krcdn.com/cover.jpg">' \
               '<script>window.initialState=' + __import__("json").dumps(state, ensure_ascii=False) + ';</script>'
        result = parse_36kr_article_page(page, "https://m.36kr.com/p/100")
        self.assertEqual(result["title"], "36氪深度文章")
        self.assertEqual(result["description"], "文章摘要")
        self.assertIn("第一段正文", result["content"])
        self.assertEqual(result["cover"], "https://img.36krcdn.com/cover.jpg")
        self.assertEqual(result["images"], [{"url": "https://img.36krcdn.com/body.jpg", "alt": "正文图"}])

    def test_parse_36kr_newsflash_uses_explicit_detail_path_without_item_id(self):
        state = {"newsflashDetail": {"detail": {
            "widgetTitle": "36氪快讯",
            "widgetContent": "快讯正文。",
        }}}
        page = '<meta name="og:url" content="https://m.36kr.com/newsflashes/200"><script>window.initialState=' + __import__("json").dumps(state, ensure_ascii=False) + ';</script>'
        result = parse_36kr_article_page(page, "https://m.36kr.com/newsflashes/200")
        self.assertEqual(result["title"], "36氪快讯")
        self.assertIn("快讯正文", result["content"])

    def test_parse_36kr_rejects_page_whose_canonical_id_does_not_match(self):
        state = {"newsflashDetail": {"detail": {"widgetTitle": "错误快讯", "widgetContent": "错误正文"}}}
        page = '<meta name="og:url" content="https://m.36kr.com/newsflashes/999"><script>window.initialState=' + __import__("json").dumps(state, ensure_ascii=False) + ';</script>'
        with self.assertRaisesRegex(ValueError, "网址不匹配"):
            parse_36kr_article_page(page, "https://m.36kr.com/newsflashes/200")

    def test_bilibili_video_url_returns_in_app_player_metadata(self):
        result = fetch_bilibili_video("https://www.bilibili.com/video/BV1xx411c7mD")
        self.assertEqual(result["kind"], "video")
        self.assertEqual(result["platform"], "bilibili")
        self.assertEqual(result["bvid"], "BV1xx411c7mD")
        self.assertIn("bvid=BV1xx411c7mD", result["embedUrl"])
        self.assertTrue(result["embedUrl"].startswith("https://player.bilibili.com/player.html"))

    def test_news_reader_is_modal_and_has_close_control(self):
        source = (Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="newsReaderModal"', source)
        self.assertIn('id="newsReaderClose"', source)
        self.assertIn("showNewsReader(b)", source)
        self.assertIn("document.querySelector('.news-reader-backdrop').onclick=closeNewsReader", source)
        self.assertIn("e.key==='Escape'", source)
        self.assertIn("$('newsArticleBody').innerHTML=''", source)
        self.assertLess(source.index("showNewsReader(b)"), source.index("await fetch(NEWS_ARTICLE_API"))

    def test_news_snapshot_has_same_origin_and_dual_cdn_fallbacks(self):
        source = (Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertIn("const NEWS_SNAPSHOT_URLS=[", source)
        self.assertIn("'./hot-news.json'", source)
        self.assertIn("gcore.jsdelivr.net/gh/alynlox-ui/HermesWeather@main/hot-news.json", source)
        self.assertIn("fastly.jsdelivr.net/gh/alynlox-ui/HermesWeather@main/hot-news.json", source)
        self.assertIn("for(let i=0;i<NEWS_SNAPSHOT_URLS.length;i++)", source)
        self.assertIn("['hermes-weather-news-alynlox-ui.onrender.com','127.0.0.1','localhost'].includes(location.hostname)?'/api/news/article'", source)
        self.assertIn("'https://hermes-weather-news-alynlox-ui.onrender.com/api/news/article'", source)


if __name__ == "__main__":
    unittest.main()
