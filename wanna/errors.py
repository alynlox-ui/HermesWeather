"""服务层错误类型：区分调用方错误与上游故障。"""


class UpstreamError(RuntimeError):
    """上游接口（Open-Meteo 等）不可达或返回非法数据 → HTTP 502。"""


class BadRequest(ValueError):
    """调用方参数错误 → HTTP 400。沿用 ValueError 便于既有 except 分支兼容。"""
