"""测试辅助：前端拆分后的聚合源码视图。

index.html 的 CSS/JS 已拆到 static/css 与 static/js，但契约测试仍希望
像过去那样在一个字符串里同时看到结构、样式与脚本。本模块按
index.html → css → js 的顺序聚合，保证：
- index.html 在最前，使 `split('const SITE_EXTRA_SOFTWARE=',1)[0]` 仍能数到
  静态卡片的 18 个 class="site-logo"；
- 同一文件内部的相对顺序不变，使 `assertLess(index(A), index(B))` 类断言继续成立。
"""
from pathlib import Path

# 单一真值版本：与 index.html meta、wanna/config.py、/health 三处交叉校验
APP_VERSION = "1.17.1-wanna-icon"
CRAWLER_REVISION = f"web-{APP_VERSION}"


def aggregate_source(root):
    """返回前端聚合文本（html + css + js）。"""
    root = Path(root)
    parts = [(root / "index.html").read_text(encoding="utf-8")]
    for folder in ("css", "js"):
        for path in sorted((root / "static" / folder).glob("*." + folder)):
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def js_bundle(root):
    """只拼接 static/js，供纯脚本断言使用。"""
    root = Path(root)
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted((root / "static" / "js").glob("*.js")))
