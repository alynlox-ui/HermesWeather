import concurrent.futures
import html
import io
import json
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image
import resvg_py

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
ICON_DIR = ROOT / "assets" / "site-icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

ADDITIONS = [
    ("games", "Playnite", "开源游戏库管理器，可把多个平台、本地游戏和模拟器统一到一个精致界面中。", "https://playnite.link/", "https://playnite.link/", "playnite 游戏库 管理 启动器 开源"),
    ("games", "Heroic Games Launcher", "开源跨平台启动器，可管理 Epic、GOG 与 Amazon Games 游戏库。", "https://heroicgameslauncher.com/", "https://heroicgameslauncher.com/downloads", "heroic games launcher epic gog amazon 开源 游戏"),
    ("games", "RetroArch", "跨平台开源模拟器前端，通过核心系统统一运行多种经典主机游戏。", "https://www.retroarch.com/", "https://www.retroarch.com/?page=platforms", "retroarch 模拟器 复古 游戏 开源"),
    ("games", "Dolphin Emulator", "成熟的 GameCube 与 Wii 开源模拟器，支持高清渲染、手柄和存档管理。", "https://dolphin-emu.org/", "https://dolphin-emu.org/download/", "dolphin emulator 海豚 gamecube wii 模拟器"),
    ("games", "PPSSPP", "高性能开源 PSP 模拟器，可提升分辨率并支持跨平台存档。", "https://www.ppsspp.org/", "https://www.ppsspp.org/download/", "ppsspp psp 模拟器 游戏 开源"),
    ("games", "Prism Launcher", "轻量开源 Minecraft 启动器，擅长多实例、模组包和版本隔离管理。", "https://prismlauncher.org/", "https://prismlauncher.org/download/", "prism launcher minecraft 我的世界 模组 启动器"),
    ("games", "Modrinth App", "面向 Minecraft 模组、整合包、插件与资源包的现代开源管理应用。", "https://modrinth.com/app", "https://modrinth.com/app", "modrinth app minecraft 模组 整合包"),
    ("games", "CurseForge", "大型游戏模组与整合包平台，覆盖 Minecraft、魔兽世界等热门游戏。", "https://www.curseforge.com/", "https://www.curseforge.com/download/app", "curseforge 模组 mod minecraft wow 游戏"),
    ("games", "Nexus Mods", "老牌游戏模组社区与管理工具入口，覆盖大量单机游戏与玩家作品。", "https://www.nexusmods.com/", "https://www.nexusmods.com/about/vortex/", "nexus mods vortex 模组 单机 游戏"),
    ("games", "Game Jolt", "独立游戏与创作者社区，可发现免费作品、Game Jams 和小众实验游戏。", "https://gamejolt.com/", "https://gamejolt.com/client", "game jolt 独立游戏 indie 社区"),
    ("games", "GeForce NOW", "NVIDIA 云游戏平台，可在普通设备串流运行已拥有的兼容 PC 游戏。", "https://www.nvidia.com/geforce-now/", "https://www.nvidia.com/en-us/geforce-now/download/", "geforce now nvidia 英伟达 云游戏 串流"),
    ("games", "Moonlight", "开源低延迟游戏串流客户端，可从支持 Sunshine 的电脑串流到多种设备。", "https://moonlight-stream.org/", "https://github.com/moonlight-stream/moonlight-qt/releases/latest", "moonlight sunshine 游戏 串流 远程 开源"),
    ("office", "Anytype", "本地优先、端到端加密的知识管理与协作工具，可离线使用并建立关联数据库。", "https://anytype.io/", "https://download.anytype.io/", "anytype 笔记 知识库 本地优先 加密"),
    ("office", "Logseq", "开源本地优先的大纲式知识库，支持双向链接、任务、白板与插件。", "https://logseq.com/", "https://logseq.com/downloads", "logseq 笔记 大纲 双向链接 本地 开源"),
    ("office", "Joplin", "开源 Markdown 笔记与待办工具，支持端到端加密和多种同步服务。", "https://joplinapp.org/", "https://joplinapp.org/help/install/", "joplin markdown 笔记 待办 加密 开源"),
    ("office", "AppFlowy", "开源、可自托管的工作空间，提供文档、数据库和项目协作能力。", "https://appflowy.io/", "https://appflowy.io/download", "appflowy 文档 数据库 协作 开源 notion 替代"),
    ("office", "CryptPad", "注重隐私的端到端加密在线办公套件，含文档、表格、白板和表单。", "https://cryptpad.org/", "https://cryptpad.org/", "cryptpad 加密 在线办公 文档 表格 隐私"),
    ("office", "Standard Notes", "简洁安全的端到端加密笔记应用，支持多端同步和离线访问。", "https://standardnotes.com/", "https://standardnotes.com/download", "standard notes 笔记 加密 隐私 同步"),
    ("dev", "Zed", "高性能协作代码编辑器，强调低延迟、多人协作与现代 AI 开发工作流。", "https://zed.dev/", "https://zed.dev/download", "zed editor 编辑器 代码 开发 协作"),
    ("dev", "Lapce", "使用 Rust 编写的快速开源代码编辑器，提供远程开发、插件与 Vim 模式。", "https://lap.dev/lapce/", "https://lap.dev/lapce/", "lapce rust 代码 编辑器 开源 开发"),
    ("dev", "Insomnia", "面向 REST、GraphQL、gRPC 的 API 设计与调试客户端，支持环境和集合。", "https://insomnia.rest/", "https://insomnia.rest/download", "insomnia api rest graphql grpc 调试 开发"),
    ("dev", "Bruno", "离线优先、Git 友好的开源 API 客户端，集合直接保存为纯文本文件。", "https://www.usebruno.com/", "https://www.usebruno.com/downloads", "bruno api 客户端 离线 git 开源 开发"),
    ("dev", "Hoppscotch", "轻量开源 Web API 开发套件，可直接在浏览器发送 REST、GraphQL 等请求。", "https://hoppscotch.io/", "https://hoppscotch.io/", "hoppscotch api rest graphql web 开源 开发"),
    ("dev", "DevToys", "面向开发者的离线工具箱，集成编码、哈希、JSON、正则与文本处理工具。", "https://devtoys.app/", "https://devtoys.app/download", "devtoys 开发者 工具箱 json regex 编码"),
    ("design", "Penpot", "开源网页端 UI/UX 设计与原型协作平台，基于开放标准并支持自托管。", "https://penpot.app/", "https://penpot.app/", "penpot ui ux 原型 设计 开源 figma 替代"),
    ("design", "Photopea", "可在浏览器运行的专业图像编辑器，支持 PSD、图层、蒙版和多种格式。", "https://www.photopea.com/", "https://www.photopea.com/", "photopea psd 图片 编辑 浏览器 设计"),
    ("design", "Aseprite", "专注像素画与 2D 动画的编辑器，适合游戏素材、精灵图和逐帧动画。", "https://www.aseprite.org/", "https://www.aseprite.org/download/", "aseprite 像素画 pixel art 动画 游戏素材"),
    ("design", "PureRef", "轻量参考图整理工具，可在无限画布中快速收集、排列和查看灵感素材。", "https://www.pureref.com/", "https://www.pureref.com/download.php", "pureref 参考图 灵感 画板 设计"),
    ("design", "darktable", "开源摄影工作流与 RAW 图像处理软件，提供非破坏编辑和色彩管理。", "https://www.darktable.org/", "https://www.darktable.org/install/", "darktable raw 摄影 修图 图片 开源"),
    ("design", "Scribus", "开源桌面出版与专业排版软件，适合书刊、海报和印刷 PDF 制作。", "https://www.scribus.net/", "https://www.scribus.net/downloads/", "scribus 排版 出版 印刷 pdf 开源 设计"),
    ("media", "mpv", "极简高性能开源媒体播放器，支持广泛格式、硬件解码和脚本扩展。", "https://mpv.io/", "https://mpv.io/installation/", "mpv 播放器 视频 音频 开源"),
    ("media", "Strawberry Music Player", "面向本地音乐收藏的开源播放器，支持标签、封面、歌词和多种音频格式。", "https://www.strawberrymusicplayer.org/", "https://www.strawberrymusicplayer.org/#download", "strawberry music player 本地音乐 播放器 开源"),
    ("media", "Jellyfin", "完全开源的个人媒体服务器，可在多设备整理和串流电影、剧集与音乐。", "https://jellyfin.org/", "https://jellyfin.org/downloads/", "jellyfin 媒体服务器 串流 影音 开源"),
    ("media", "LosslessCut", "跨平台无损视频音频剪切工具，可快速裁切、合并和重新封装媒体文件。", "https://mifi.no/losslesscut/", "https://github.com/mifi/lossless-cut/releases/latest", "losslesscut 无损 视频 剪切 合并 影音"),
    ("media", "Kdenlive", "功能完整的开源非线性视频编辑器，支持多轨道、代理和丰富效果。", "https://kdenlive.org/", "https://kdenlive.org/download/", "kdenlive 视频 剪辑 非线性 开源"),
    ("media", "OpenShot", "易上手的开源视频编辑器，提供多轨道、动画、标题和常用转场。", "https://www.openshot.org/", "https://www.openshot.org/download/", "openshot 视频 剪辑 动画 开源"),
    ("utilities", "QuickLook", "为 Windows 带来按空格快速预览文件的体验，支持图片、文档、视频等格式。", "https://github.com/QL-Win/QuickLook", "https://github.com/QL-Win/QuickLook/releases/latest", "quicklook windows 文件 快速预览 工具"),
    ("utilities", "Flow Launcher", "开源 Windows 快速启动器，可搜索应用、文件、网页并通过插件扩展。", "https://www.flowlauncher.com/", "https://www.flowlauncher.com/download", "flow launcher windows 启动器 搜索 效率 工具"),
    ("utilities", "Ditto", "开源 Windows 剪贴板历史管理器，可搜索、同步并快速粘贴历史内容。", "https://ditto-cp.sourceforge.io/", "https://ditto-cp.sourceforge.io/", "ditto 剪贴板 历史 windows 开源 工具"),
    ("utilities", "WizTree", "高速磁盘空间分析工具，可直观定位占用大量空间的文件和目录。", "https://diskanalyzer.com/", "https://diskanalyzer.com/download", "wiztree 磁盘 空间 分析 大文件 工具"),
    ("utilities", "Bulk Crap Uninstaller", "开源批量卸载工具，可检测残留、静默卸载并清理大量程序。", "https://www.bcuninstaller.com/", "https://www.bcuninstaller.com/", "bulk crap uninstaller bcu 批量 卸载 清理 开源"),
    ("utilities", "EarTrumpet", "增强 Windows 音量控制的开源工具，可分别管理每个应用和音频设备。", "https://eartrumpet.app/", "https://eartrumpet.app/", "eartrumpet windows 音量 混音器 音频 工具"),
]

BRAND_ICON_OVERRIDES = {
    "Ubisoft Connect": ("ubisoft", "FFFFFF"),
    "EA app": ("ea", "FFFFFF"),
    "Epic Games": ("epicgames", "FFFFFF"),
    "Battle.net": ("battledotnet", "148EFF"),
}
BRAND_SVG_URL_OVERRIDES = {
    "Xbox": "https://upload.wikimedia.org/wikipedia/commons/f/f9/Xbox_one_logo.svg",
}


def slugify(name):
    aliases = {
        "腾讯会议": "tencent-meeting",
        "钉钉": "dingtalk",
        "飞书": "feishu",
        "网易云音乐": "netease-cloud-music",
    }
    if name in aliases:
        return aliases[name]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "site"


def request_bytes(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        data = resp.read(3_000_001)
        if len(data) > 3_000_000:
            raise ValueError("icon too large")
        return data, resp.geturl(), resp.headers.get("Content-Type", "")


def page_icon_candidates(official):
    parsed = urllib.parse.urlparse(official)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = []
    try:
        page, final, ctype = request_bytes(official, 12)
        if "html" in ctype.lower() or page.lstrip().startswith(b"<"):
            text = page.decode("utf-8", "ignore")
            for tag in re.findall(r"<link\b[^>]*>", text, re.I):
                if re.search(r"rel\s*=\s*['\"][^'\"]*(?:icon|apple-touch-icon)[^'\"]*['\"]", tag, re.I):
                    match = re.search(r"href\s*=\s*['\"]([^'\"]+)['\"]", tag, re.I)
                    if match:
                        candidates.append(urllib.parse.urljoin(final, html.unescape(match.group(1))))
    except Exception:
        pass
    candidates += [origin + "/favicon.ico", origin + "/favicon.png", origin + "/apple-touch-icon.png"]
    # Last-resort caches still return the site's published favicon; files are stored locally after validation.
    host = parsed.hostname or ""
    candidates += [
        "https://icon.horse/icon/" + host,
        "https://www.google.com/s2/favicons?sz=128&domain_url=" + urllib.parse.quote(official, safe=""),
        "https://icons.duckduckgo.com/ip3/" + host + ".ico",
    ]
    return list(dict.fromkeys(candidates))


def save_png(data, target):
    with Image.open(io.BytesIO(data)) as im:
        im.seek(0)
        im = im.convert("RGBA")
        bbox = im.getchannel("A").getbbox()
        if bbox:
            im = im.crop(bbox)
        scale = min(112 / max(im.width, 1), 112 / max(im.height, 1))
        size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
        im = im.resize(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        canvas.alpha_composite(im, ((128 - im.width) // 2, (128 - im.height) // 2))
        canvas.save(target, "PNG", optimize=True)


def apply_brand_overrides():
    applied = []
    for name, (simple_icon, color) in BRAND_ICON_OVERRIDES.items():
        svg, final, _ = request_bytes(f"https://cdn.simpleicons.org/{simple_icon}/{color}", 20)
        png = resvg_py.svg_to_bytes(svg_string=svg.decode("utf-8"), width=256, height=256)
        target = ICON_DIR / (slugify(name) + ".png")
        save_png(png, target)
        applied.append({"name": name, "source": final, "file": target.name})
    for name, url in BRAND_SVG_URL_OVERRIDES.items():
        svg, final, _ = request_bytes(url, 20)
        png = resvg_py.svg_to_bytes(svg_string=svg.decode("utf-8"), width=256, height=256)
        target = ICON_DIR / (slugify(name) + ".png")
        save_png(png, target)
        applied.append({"name": name, "source": final, "file": target.name})
    return applied


def download_icon(item):
    name, official = item
    target = ICON_DIR / (slugify(name) + ".png")
    if target.is_file() and target.stat().st_size > 100:
        return {"name": name, "file": target.name, "source": "existing-local-cache", "bytes": target.stat().st_size}
    errors = []
    for candidate in page_icon_candidates(official):
        try:
            data, final, _ = request_bytes(candidate, 12)
            save_png(data, target)
            return {"name": name, "file": target.name, "source": final, "bytes": target.stat().st_size}
        except Exception as exc:
            errors.append(type(exc).__name__)
    return {"name": name, "file": target.name, "error": ",".join(errors[-4:])}


def js(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")


def main():
    source = INDEX.read_text(encoding="utf-8")
    source = source.replace('content="1.14.0-sites-expanded"', 'content="1.15.0-niche-sites-icons"', 1)

    existing_dynamic = source.split("const SITE_EXTRA_SOFTWARE=[", 1)[1].split("];", 1)[0]
    existing = []
    for line in existing_dynamic.splitlines():
        if not line.startswith("{cat:"):
            continue
        fields = {k: re.search(k + r":'((?:\\'|[^'])*)'", line).group(1).replace("\\'", "'") for k in ("cat", "name", "icon", "desc", "official", "download", "keywords")}
        existing.append(fields)

    new_records = [dict(cat=cat, name=name, icon="", desc=desc, official=official, download=download, keywords=keywords) for cat, name, desc, official, download, keywords in ADDITIONS]
    records = existing + new_records
    if len(records) != 96:
        raise RuntimeError(f"expected 96 dynamic records, got {len(records)}")

    static_matches = []
    static_source = source.split("const SITE_EXTRA_SOFTWARE=", 1)[0]
    for match in re.finditer(r'<article class="site-card"[^>]*>.*?<span class="site-card-icon">.*?</span><h3>(.*?)</h3>.*?<a class="site-official" href="([^"]+)"', static_source, re.S):
        static_matches.append((html.unescape(re.sub("<.*?>", "", match.group(1))), match.group(2)))
    # The broad regex can cross articles; retain unique names in source order.
    static = []
    seen = set()
    for item in static_matches:
        if item[0] not in seen:
            seen.add(item[0]); static.append(item)
    if len(static) != 18:
        raise RuntimeError(f"expected 18 static cards, got {len(static)}: {static}")

    all_sites = static + [(x["name"], x["official"]) for x in records]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        report = list(pool.map(download_icon, all_sites))
    failures = [x for x in report if "error" in x]
    if failures:
        (ROOT / "site-icon-download-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"icon download failures: {failures}")
    overrides = apply_brand_overrides()
    for icon_file in ICON_DIR.glob("*.png"):
        save_png(icon_file.read_bytes(), icon_file)

    static_prefix, static_suffix = source.split("const SITE_EXTRA_SOFTWARE=", 1)
    replaced_names = []
    def replace_static_card(match):
        article = match.group(0)
        name_match = re.search(r"<h3>(.*?)</h3>", article, re.S)
        if not name_match:
            return article
        name = html.unescape(re.sub("<.*?>", "", name_match.group(1)))
        path = "assets/site-icons/" + slugify(name) + ".png"
        replacement = '<span class="site-card-icon"><img class="site-logo" src="' + path + '" alt="" loading="lazy" decoding="async"></span>'
        updated, count = re.subn(r'<span class="site-card-icon">.*?</span>', replacement, article, count=1, flags=re.S)
        if count == 1:
            replaced_names.append(name)
        return updated
    static_prefix = re.sub(r'<article class="site-card"[^>]*>.*?</article>', replace_static_card, static_prefix, flags=re.S)
    if len(replaced_names) != 18:
        raise RuntimeError(f"failed static icon replacements: {replaced_names}")
    source = static_prefix + "const SITE_EXTRA_SOFTWARE=" + static_suffix

    lines = []
    for x in records:
        icon = "assets/site-icons/" + slugify(x["name"]) + ".png"
        lines.append("{cat:'%s',name:'%s',icon:'%s',desc:'%s',official:'%s',download:'%s',keywords:'%s'}," % tuple(js(v) for v in (x["cat"], x["name"], icon, x["desc"], x["official"], x["download"], x["keywords"])))
    lines[-1] = lines[-1].rstrip(",")
    new_array = "const SITE_EXTRA_SOFTWARE=[\n" + "\n".join(lines) + "\n];"
    source = re.sub(r"const SITE_EXTRA_SOFTWARE=\[.*?\];", new_array, source, count=1, flags=re.S)

    old_renderer = "function siteCardHTML(x){return '<article class=\"site-card\" data-search=\"'+escapeHTML(x.keywords+' '+x.name)+'\"><span class=\"site-card-icon\">'+escapeHTML(x.icon)+'</span><h3>'+escapeHTML(x.name)+'</h3><p>'+escapeHTML(x.desc)+'</p><div class=\"site-actions\"><a class=\"site-official\" href=\"'+escapeHTML(x.official)+'\" target=\"_blank\" rel=\"noopener noreferrer\">访问官网</a><a class=\"site-download\" href=\"'+escapeHTML(x.download)+'\" target=\"_blank\" rel=\"noopener noreferrer\">官方下载</a></div></article>'}"
    new_renderer = "function siteIconHTML(x){return '<span class=\"site-card-icon\"><img class=\"site-logo\" src=\"'+escapeHTML(x.icon)+'\" alt=\"\" loading=\"lazy\" decoding=\"async\"></span>'}\nfunction siteCardHTML(x){return '<article class=\"site-card\" data-search=\"'+escapeHTML(x.keywords+' '+x.name)+'\">'+siteIconHTML(x)+'<h3>'+escapeHTML(x.name)+'</h3><p>'+escapeHTML(x.desc)+'</p><div class=\"site-actions\"><a class=\"site-official\" href=\"'+escapeHTML(x.official)+'\" target=\"_blank\" rel=\"noopener noreferrer\">访问官网</a><a class=\"site-download\" href=\"'+escapeHTML(x.download)+'\" target=\"_blank\" rel=\"noopener noreferrer\">官方下载</a></div></article>'}"
    if old_renderer not in source:
        raise RuntimeError("siteCardHTML renderer not found")
    source = source.replace(old_renderer, new_renderer, 1)

    source = source.replace("</style></head>", ".site-card-icon{overflow:hidden}.site-logo{display:block;width:100%;height:100%;object-fit:contain;border-radius:9px}\n</style></head>", 1)
    INDEX.write_text(source, encoding="utf-8")
    (ROOT / "site-icon-download-report.json").write_text(json.dumps({"downloaded": report, "brandOverrides": overrides}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dynamic": len(records), "static": len(static), "icons": len(report), "icon_bytes": sum(x["bytes"] for x in report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
