import json
import unittest
from pathlib import Path

from refresh_hot_news_snapshot import parse_36kr_initial_state, parse_qbitai_posts

ROOT = Path(__file__).resolve().parents[1]


class HotNewsSourceTests(unittest.TestCase):
    def test_parse_qbitai_posts_keeps_article_identity_summary_and_cover(self):
        posts = [{
            "link": "https://www.qbitai.com/2026/08/467196.html",
            "date": "2026-08-06T07:52:10",
            "title": {"rendered": "量子位 AI 新闻"},
            "excerpt": {"rendered": "<p>量子位摘要</p>"},
            "_embedded": {"wp:featuredmedia": [{"source_url": "https://static.qbitai.com/cover.jpg"}]},
        }]
        rows = parse_qbitai_posts(posts)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "量子位 AI 新闻")
        self.assertEqual(rows[0]["url"], posts[0]["link"])
        self.assertEqual(rows[0]["desc"], "量子位摘要")
        self.assertEqual(rows[0]["cover"], "https://static.qbitai.com/cover.jpg")
        self.assertEqual(rows[0]["platform"], "qbitai")

    def test_parse_qbitai_posts_rejects_invalid_api_shape(self):
        with self.assertRaisesRegex(ValueError, "list"):
            parse_qbitai_posts({"error": "rate limited"})

    def test_parse_36kr_initial_state_keeps_articles_and_newsflashes_with_images(self):
        state = {
            "newsflashList": {
                "banner": [{
                    "itemId": 100,
                    "templateMaterial": {
                        "widgetTitle": "36氪 AI 深度文章",
                        "widgetImage": "https://img.36krcdn.com/article.jpg",
                        "publishTime": 1700000000000,
                    },
                }],
                "flow": {"itemList": [{
                    "itemId": 200,
                    "templateMaterial": {
                        "widgetTitle": "36氪 AI 快讯",
                        "widgetContent": "快讯正文摘要",
                        "widgetImage": "https://img.36krcdn.com/flash.jpg",
                        "publishTime": 1700000001000,
                    },
                }]},
            }
        }
        page = "<script>window.initialState=" + json.dumps(state, ensure_ascii=False) + ";</script>"
        rows = parse_36kr_initial_state(page)
        self.assertEqual([x["title"] for x in rows], ["36氪 AI 深度文章", "36氪 AI 快讯"])
        self.assertEqual(rows[0]["url"], "https://m.36kr.com/p/100")
        self.assertEqual(rows[0]["cover"], "https://img.36krcdn.com/article.jpg")
        self.assertEqual(rows[1]["url"], "https://m.36kr.com/newsflashes/200")
        self.assertEqual(rows[1]["desc"], "快讯正文摘要")
        self.assertEqual(rows[1]["platform"], "36kr")

    def test_frontend_replaces_international_sources_with_ai_zone(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for removed in ('data-news-source="international"', 'data-news-source="x"',
                        'data-news-source="instagram"', 'data-news-source="tiktok"'):
            self.assertNotIn(removed, source)
        self.assertIn('data-news-source="qbitai"', source)
        self.assertIn('data-news-source="36kr"', source)
        self.assertIn('data-news-source="ai"', source)
        self.assertIn("ai:{label:'AI专区',routes:['qbitai','36kr']}", source)
        self.assertIn("data.images", source)
        self.assertIn("data.contentBlocks", source)
        self.assertIn("news-article-image", source)
        self.assertIn("function safeBilibiliEmbed", source)
        self.assertIn("u.protocol==='https:'&&u.hostname==='player.bilibili.com'", source)
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-presentation"', source)

    def test_snapshot_config_has_no_social_sources(self):
        source = (ROOT / "refresh_hot_news_snapshot.py").read_text(encoding="utf-8")
        self.assertIn('"qbitai"', source)
        self.assertIn('"36kr"', source)
        self.assertNotIn("INTERNATIONAL=", source)
        self.assertNotIn("fetch_social", source)


if __name__ == "__main__":
    unittest.main()
