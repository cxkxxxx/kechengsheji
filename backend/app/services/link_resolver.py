"""把用户发来的商品链接/分享文案解析成结构化信息。

只做字符串解析，不发任何外部请求：平台识别靠域名，商品 ID 靠 URL 路径或查询参数，
搜索词从 URL 的标题参数或分享文案的书名号里抽。解析不出来时返回 keyword=None，
由上层用原文兜底。
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

_URL_RE = re.compile(r"https?://[^\s，,、”\"'<>()（]+", re.I)

# (平台名, 域名匹配, 取 ID 的路径正则)
_RULES = [
    ("京东", re.compile(r"(^|\.)jd\.com$", re.I),
     [re.compile(r"/(?:product/view|sku)/(\d{6,})"), re.compile(r"/(\d{6,})\.html")]),
    ("天猫", re.compile(r"(^|\.)tmall\.(com|cn)$", re.I), [re.compile(r"/item/(\d{6,})")]),
    ("淘宝", re.compile(r"(^|\.)taobao\.(com|cn)$", re.I), [re.compile(r"/item\.htm")]),
    ("拼多多", re.compile(r"(^|\.)yangkeduo\.com$|(^|\.)pinduoduo\.com$", re.I), []),
    ("苏宁", re.compile(r"(^|\.)suning\.com$", re.I),
     [re.compile(r"/(\d{8,})\.shtml"), re.compile(r"/(\d{6,})\.html")]),
    ("唯品会", re.compile(r"(^|\.)vip\.com$", re.I), [re.compile(r"/detail-(\d{6,})")]),
    ("抖音商城", re.compile(r"haohuo\.jinritemai\.com$|(^|\.)douyin\.com$", re.I), []),
]

_ID_QUERY_KEYS = ["id", "goods_id", "goodsId", "product_id", "productId", "sku_id", "skuId", "item_id"]
_TITLE_QUERY_KEYS = ["wareName", "title", "subject", "goodsName", "share_title", "itemName", "name"]

# 分享文案里的引导语，抽词时要去掉
_NOISE = re.compile(
    r"复制(此|这)?(条|段)?(消息|链接|内容)|打开\s*\S{0,4}(App|app|客户端)|长按|粘贴到|"
    r"查看详情|立即|抢购|优惠|领券|红包|折扣|自营|包邮|新品|爆款|正品|天猫|京东|拼多多|淘宝|商城|官方|旗舰店|"
    r"【|】|\[|\]|\(1\)|https?://\S+", re.I)
# 品牌外文括注：「戴森（Dyson）V12」要连成「戴森V12」，否则括号把品牌和产品名切断
_PAREN = re.compile(r"[（(][^）)]{0,24}[）)]")
# 口语指代词：抽词时连同「帮我看看这个值不值」一起剪掉，剩下的才是商品名
_CHAT_WORDS = re.compile(r"帮我|我看|看下|这个|那个|这件|那件|值不值|怎么|哪个|哪家|是不是|求|推荐|买|比价|多少|划算")
# 电商标题几乎都包在【】里，「」是次要写法
_BRACKET = re.compile(r"[「『【]([^」』】]{4,40})[」』】]")
_SUFFIX = re.compile(r"([一-龥A-Za-z0-9+\-·]{6,40}(?:旗舰店|官方|Pro|Plus|代|版|机|器|套装))")


def _qs(url: str) -> dict:
    try:
        return {k.lower(): v for k, v in parse_qs(urlparse(url).query, keep_blank_values=False).items()}
    except ValueError:
        return {}


def _runs(text: str) -> list:
    """切出像商品名的片段：至少 4 个字，去掉首尾空白造成的假长度。"""
    out = []
    for r in re.findall(r"[一-龥A-Za-z0-9][一-龥A-Za-z0-9 +\-·]{3,40}", text):
        r = re.sub(r"\s+", " ", r).strip()
        if len(r) >= 4:
            out.append(r)
    return out


def _guess_keyword(text: str) -> str:
    """从分享文案里抽商品名：优先括号内的标题，其次去掉引导语与口语词后最长的一段中文。"""
    text = _PAREN.sub("", text or "")
    m = re.search(_BRACKET, text)
    if m:
        return m.group(1).strip()
    # 括号外的口语指代词一律当断点，否则「帮我看看这个戴森吸尘器」会整段被当成商品名去搜
    bare = _CHAT_WORDS.sub("|", text)
    m = re.search(_SUFFIX, bare)
    if m:
        return m.group(1).strip()
    runs = _runs(_NOISE.sub(" ", _URL_RE.sub(" ", bare)))
    return max(runs, key=len) if runs else ""


def resolve(text: str) -> dict:
    """→ {platform, goods_id, url, keyword, title_from_url, all_urls}"""
    text = text or ""
    urls = [u.rstrip(".,;:;。") for u in _URL_RE.findall(text)]
    result = {"platform": "", "goods_id": "", "url": urls[0] if urls else "",
              "keyword": "", "title_from_url": "", "all_urls": urls}
    if not urls:
        result["keyword"] = _guess_keyword(text)
        return result

    host = ""
    try:
        host = urlparse(urls[0]).hostname or ""
    except ValueError:
        host = ""
    qs = _qs(urls[0])

    for name, host_re, path_res in _RULES:
        if not host or not host_re.search(host):
            continue
        result["platform"] = name
        for key in _ID_QUERY_KEYS:
            if qs.get(key.lower()):
                result["goods_id"] = qs[key.lower()][0]
                break
        if not result["goods_id"]:
            path = urlparse(urls[0]).path or ""
            for r in path_res:
                m = r.search(path)
                if m and m.groups():
                    result["goods_id"] = m.group(1)
                    break
        break

    for key in _TITLE_QUERY_KEYS:
        if qs.get(key.lower()):
            result["title_from_url"] = unquote(qs[key.lower()][0])
            break
    result["keyword"] = result["title_from_url"] or _guess_keyword(text)
    return result
