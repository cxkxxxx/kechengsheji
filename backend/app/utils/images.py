"""帖子/攻略的图片字段：库里存的是一个 JSON 数组字符串，读写都收口到这里。"""
import json


def loads(raw: str) -> list:
    """把 images 字段解成 URL 列表。脏数据一律当成没图，别让列表接口 500。"""
    if not raw:
        return []
    try:
        got = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [u for u in got if isinstance(u, str)] if isinstance(got, list) else []


def dumps(urls, limit: int, field: str = "图片") -> str:
    """校验并序列化。

    只接受本站 /static/ 下的地址：这个字段会渲染进所有用户看到的卡片里，
    放开成任意 URL 就等于让人往公开内容里塞外链跳转或追踪像素。
    """
    clean = []
    for u in urls or []:
        u = (u or "").strip()
        if not u:
            continue
        if not u.startswith("/static/") or ".." in u:
            raise ValueError("%s只能是本站上传后返回的 /static/ 链接" % field)
        if u not in clean:
            clean.append(u)
    if len(clean) > limit:
        raise ValueError("%s最多 %d 张，当前提交了 %d 张" % (field, limit, len(clean)))
    return json.dumps(clean, ensure_ascii=False)
