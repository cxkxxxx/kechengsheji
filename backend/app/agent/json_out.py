"""AI 输出的 JSON 解析与校验工具。

glm-4-flash 是普通对话模型，不保证纯 JSON 输出，常见三种脏形态：
1. 整段包在 ```json ... ``` 代码块里；
2. JSON 前后带一句「好的，以下是...」之类的话；
3. JSON 里有多余尾逗号（极少数）。
这里统一剥壳后解析，解析失败抛 AIOutputError，由路由转成 502 让用户重试。
绝不拿「解析失败的文本」当结果返给前端冒充成功。
"""

import json
import logging
import re

log = logging.getLogger("ai_json")


class AIOutputError(RuntimeError):
    """模型输出不符合约定格式。brief 给用户看，detail 进日志。"""

    def __init__(self, brief: str, detail: str = ""):
        super().__init__(brief)
        self.brief = brief
        self.detail = detail or brief


def extract_json(text: str) -> dict:
    """从模型回复里抠出第一个完整 JSON 对象。抠不出就抛 AIOutputError。"""
    s = (text or "").strip()
    if not s:
        raise AIOutputError("AI 没有返回内容，请重试一次", "empty response")

    # 先剥 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    else:
        # 没围栏就取第一个 { 到最后一个 } 之间的内容（模型爱在前后加客套话）
        start, end = s.find("{"), s.rfind("}")
        if start >= 0 and end > start:
            s = s[start:end + 1]

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # 宽限一次：去掉尾逗号再试
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", s))
        except json.JSONDecodeError as e:
            log.warning("AI JSON parse failed: %.300s", text)
            raise AIOutputError("AI 返回的格式不对，请重试一次",
                                "json decode error: %s; head: %.200s" % (e, text))

    if not isinstance(data, dict):
        raise AIOutputError("AI 返回的格式不对，请重试一次",
                            "expected object, got %s" % type(data).__name__)
    return data


def _clean_str(v, limit: int) -> str:
    return str(v or "").strip()[:limit]


def _clean_list_str(v, max_items: int, item_limit: int = 200) -> list:
    """字符串列表清洗：None/标量/超长/超量都兜住。"""
    if isinstance(v, str):
        v = [x for x in re.split(r"[、,，;；\n]", v) if x.strip()]
    if not isinstance(v, list):
        return []
    out = []
    for x in v[:max_items]:
        s = _clean_str(x, item_limit)
        if s:
            out.append(s)
    return out
