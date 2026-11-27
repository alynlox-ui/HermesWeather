"""天气服务：Open-Meteo 地理编码 + 7 日预报（纯标准库）。

对照旧 weather_web.py 的修复点：
- 顶层正常 import re，去掉 __import__('re') 内联写法；
- 丢弃异常链改为 raise ... from last，保留诊断信息；
- 上游不可达抛 UpstreamError（路由层映射 502），参数错误抛 BadRequest（400）；
- 请求函数支持注入 urlopen，便于单测。
对外响应结构保持 {"place", "data", "query"} 不变。
"""
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import config
from .errors import BadRequest, UpstreamError

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_CITY = "北京"

ALIASES = {
    "纽约": "New York", "洛杉矶": "Los Angeles", "旧金山": "San Francisco",
    "华盛顿": "Washington", "伦敦": "London", "巴黎": "Paris", "东京": "Tokyo",
    "大阪": "Osaka", "首尔": "Seoul", "莫斯科": "Moscow", "悉尼": "Sydney",
    "墨尔本": "Melbourne", "新加坡": "Singapore", "曼谷": "Bangkok", "迪拜": "Dubai",
    "罗马": "Rome", "柏林": "Berlin", "马德里": "Madrid", "温哥华": "Vancouver",
    "多伦多": "Toronto",
}

ADMIN_SUFFIXES = ("自治县", "自治州", "新区", "街道", "地区", "区", "县", "市", "镇", "乡")

_CURRENT_FIELDS = "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation"
_DAILY_FIELDS = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunset"


def _get_json(url, params, opener=urlopen):
    """GET 上游 JSON，失败重试一次；两次都失败视为上游故障。"""
    last = None
    for attempt in range(config.UPSTREAM_RETRIES):
        try:
            req = Request(url + "?" + urlencode(params),
                          headers={"User-Agent": f"AllContainedWeb/{config.APP_VERSION}",
                                   "Accept": "application/json"})
            with opener(req, timeout=config.UPSTREAM_TIMEOUT) as resp:
                return json.load(resp)
        except Exception as exc:  # 网络/解码/上游 5xx 一律按可重试处理
            last = exc
            if attempt + 1 < config.UPSTREAM_RETRIES:
                time.sleep(config.UPSTREAM_RETRY_DELAY)
    raise UpstreamError("无法连接 Open-Meteo 天气服务，请检查网络或稍后重试") from last


def geocode(term, language="zh", opener=urlopen):
    payload = _get_json(GEOCODE_URL, {"name": term, "count": 20, "language": language, "format": "json"}, opener)
    return payload.get("results", [])


def _candidate_terms(raw, target, stripped, query):
    terms = []
    for term in (query, target, stripped):
        if term and term not in terms:
            terms.append(term)
    return terms


def _score(x, contexts, target, stripped, query):
    fields = " ".join(str(x.get(k) or "") for k in ("name", "admin1", "admin2", "admin3", "country")).lower()
    context_score = sum(100000000 for c in contexts if c and c in fields)
    name = str(x.get("name") or "").lower()
    exact = 300000000 if name in (target.lower(), stripped.lower(), query.lower()) else 0
    feature = 50000000 if str(x.get("feature_code", "")).startswith(("PPL", "ADM")) else 0
    return context_score + exact + feature + (x.get("population") or 0)


def lookup_weather(city, opener=urlopen):
    """按“省/市/区/镇”自由写法查询地点并取 7 日预报。"""
    raw = (city or "").strip()
    if not raw:
        raise BadRequest("地点名称不能为空")

    # 支持“省/市/区/镇”、空格、逗号等层级写法；末级作为查询目标，上级用于消除同名地点。
    parts = [x.strip() for x in re.split(r"[/,，>\s]+", raw) if x.strip()]
    target = parts[-1]
    stripped = target
    for suffix in ADMIN_SUFFIXES:
        if stripped.endswith(suffix) and len(stripped) > len(suffix):
            stripped = stripped[: -len(suffix)]
            break
    query = ALIASES.get(target, target)

    results = []
    for term in _candidate_terms(raw, target, stripped, query):
        languages = ["en", "zh"] if term != target and term in ALIASES.values() else ["zh", "en"]
        for language in languages:
            rows = geocode(term, language, opener)
            if rows:
                results.extend(rows)
                break

    # 某些区镇仅能通过拼音/英文检索；仍找不到时给出明确格式提示。
    if not results:
        raise BadRequest(f"找不到“{raw}”。区或镇请尝试“上级城市/区镇名”，如“北京/海淀”或输入拼音")

    # 去重并根据用户给出的省市区上下文、精确名称、人口进行排序。
    unique = {}
    for x in results:
        unique[(x.get("latitude"), x.get("longitude"))] = x
    contexts = [x.lower().replace("省", "").replace("市", "").replace("区", "").replace("县", "").replace("镇", "")
                for x in parts[:-1]]
    chosen = max(unique.values(), key=lambda x: _score(x, contexts, target, stripped, query))

    data = _get_json(FORECAST_URL, {
        "latitude": chosen["latitude"], "longitude": chosen["longitude"],
        "current": _CURRENT_FIELDS, "daily": _DAILY_FIELDS,
        "timezone": "auto", "forecast_days": 7,
    }, opener)
    return {"place": chosen, "data": data, "query": raw}
