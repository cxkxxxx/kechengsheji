"""京东/天猫实时比价：给 best-price-mcp 包一层自己的搜索与挑选。

三条必须知道的实情（都是实测出来的）：
1. 它的数据源不是官方开放平台，而是包作者自建的腾讯云函数中转，URL 和 token 硬编码在包里、
   所有使用者共用一份。所以有共享日配额，京东那一侧实测会整天报「已达接口调用上限」。
2. 搜索关键词会离开我们的服务器发给这个第三方，所以这里只允许传商品名，绝不把用户身份、
   账单内容、token 拼进去。
3. 它自带的挑选逻辑不可信：实测「影石Ace Pro 2」的 11 条候选里 ¥2548 的真机排第一，
   它却把 ¥16.6 的收纳包当最低价推荐给我们。所以我们只借它的抓取（_search_jd/_search_taobao），
   候选列表拿回来自己挑。它这些都是下划线开头的内部函数，不是承诺稳定的接口，
   因此全部 try 兜住，任何异常都降级成警告而不是让 AI 对话报错。
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app.core.config import PRICE_TIMEOUT

log = logging.getLogger("price")

PLATFORM_NAMES = {"jd": "京东", "taobao": "天猫"}

# 上游是搜索引擎式的，电商标题里那堆营销词会让召回直接变空：实测 42 字的
# 「DJI/大疆Osmo Action 4运动骑行相机高清防抖旅游防水vlog摄像机」零结果，
# 洗成「大疆Osmo Action 4」就有结果。
_MARKETING = re.compile(
    r"政府补贴|国补|学生优惠|分期免息|终身质保|顺丰闪发|新品|新款|上市|正品|官方旗舰|旗舰店|旗舰版|"
    r"高清|防抖|防水|旅游|旅行|骑行|运动|便携|家用|智能|专业|入门|迷你|包邮|满减|秒杀|特价|爆款|"
    r"自拍|神器|超清|增透|摄像机|相机|影像")
# 只删【营销标签】和[xx]，不删「商品标题」——淘宝分享文案里书名号包的就是标题本身
_BRACKET = re.compile(r"[【\[][^】\]]{0,30}[】\]]")
_URL = re.compile(r"https?://\S+")
_NOISE_PHRASE = re.compile(r"点击链接\S{0,6}|直接打开|或者\S{0,6}搜索|复制(此|这)?(条|段)?\S{0,8}|打开\S{0,4}(App|app|客户端)")
_SEP = re.compile(r"[\s/、,，。()（）\-+·&*「」『』]+")

# 周边配件：命中就不当成商品本体（就是它把 ¥16.6 收纳包端给我们的那类东西）
_ACCESSORY = ("钢化膜", "贴膜", "屏幕膜", "保护膜", "秒贴", "保护壳", "防水壳", "兔笼", "支架", "手持杆",
              "延长杆", "车把夹", "胸带", "头带", "背带", "挂绳", "收纳包", "收纳袋", "配件", "合集",
              "滤镜", "电池", "充电器", "充电头", "数据线", "底座", "遥控器", "镜头盖", "转接头",
              "清洁", "贴纸", "皮套", "硅胶套", "包袋", "保护套")

# 上游最坏会 15 秒 × 多组关键词 × 两个平台串起来重试，用户只能盯着「正在思考」，
# 所以压低到和 PRICE_TIMEOUT 一致。
_CONNECT_TIMEOUT = max(3.0, min(float(PRICE_TIMEOUT), 15.0))

_MODEL_TOKEN = re.compile(r"[a-z]{2,}\d+[a-z]?|\d{2,}")
# 相关性：整批都低于这个分就当没匹配到。实测真·小米15 = 1.00，堆了「小米手机」关键词的
# Redmi Note 15 = 0.50，所以不能只看绝对门槛（用户就是来比一张 ¥0.50 档位的钢化膜时
# 固定门槛会把正确答案也滤掉），改成「与最高分相差 REL_BAND 以内才算同一档」。
MIN_RELEVANCE = 0.3
REL_BAND = 0.2
# 最低价与中位价差这么多，多半是配件、单件或不同型号混进来了
_SUSPECT_RATIO = 5.0


def backend() -> dict:
    """数据源状态，给 /price/status 和启动横幅用。"""
    try:
        import best_price_mcp
    except Exception as e:
        return {"ok": False, "reason": "best-price-mcp 未安装或导入失败：%s" % str(e)[:160]}
    return {"ok": True, "reason": "", "timeout": _CONNECT_TIMEOUT}


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _norm(s: str) -> str:
    """比对用：小写、去掉空格与分隔符，「影石Ace Pro 2」和「影石AcePro2」要能对上。"""
    return _SEP.sub("", (s or "").lower())


def _clean(keyword: str) -> str:
    s = _URL.sub(" ", keyword or "")
    s = _BRACKET.sub(" ", s)
    s = _NOISE_PHRASE.sub(" ", s)
    s = _MARKETING.sub("", s)
    return _SEP.sub(" ", s).strip()


def _candidates(keyword: str) -> list:
    """清洗后的优先，原样兜底，最多两个（每次上游请求都算共享配额）。"""
    out = []
    for c in (_clean(keyword), (keyword or "").strip()):
        if c and c not in out:
            out.append(c)
    return out[:2]


def _search_one(platform: str, kw: str) -> tuple:
    """调上游拿整条候选列表。返回 (items, 原始报错文案)。"""
    import best_price_mcp
    fn = best_price_mcp._search_jd if platform == "jd" else best_price_mcp._search_taobao
    try:
        rows = fn(kw)
    except Exception as e:
        log.exception("%s 比价搜索失败", platform)
        return [], str(e)[:120]
    return list(rows or []), ""


def _item(platform: str, raw: dict) -> dict:
    raw = raw or {}
    price = _num(raw.get("price"))
    final = _num(raw.get("final_price")) or price
    url = raw.get("buy_url") or ""
    if url and not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return {
        "platform": PLATFORM_NAMES.get(platform, platform),
        "title": raw.get("name") or "",
        "price": price,
        "final_price": final,
        "coupon_amount": _num(raw.get("saved")),
        "shop": raw.get("shop") or "",
        "sales": raw.get("sales"),
        "rating": raw.get("rating"),
        "url": url,
        "source": "实时比价",
    }


def _is_accessory(title: str) -> bool:
    title = title or ""
    # 「相机膜」「镜头膜」这类写法太多，单独按结尾字判一下
    return any(a in title for a in _ACCESSORY) or title.rstrip().endswith("膜")


def _matches(title: str, kw: str) -> bool:
    """标题是不是真的在说这个商品。

    带型号时必须同时命中型号 token 和关键词里的中文词——只卡数字会串台：
    实测「小米15 手机」光匹配 "15" 会把 Redmi Note 15 当成结果推出去。
    """
    q, t = _norm(_clean(kw)), _norm(title)
    if not q or not t:
        return False
    if q in t or t in q:
        return True
    tokens = _MODEL_TOKEN.findall(q)
    if tokens:
        words = re.findall(r"[一-鿿]{2,}", q)
        return all(tok in t for tok in tokens) and all(w in t for w in words)
    return len(q) >= 4      # 没有型号信息时（如「空气炸锅」）按字面宽松匹配


def _is_accessory(title: str) -> bool:
    title = title or ""
    # 「相机膜」「镜头膜」这类写法太多，兜一下以「膜」结尾的
    return any(a in title for a in _ACCESSORY) or title.rstrip().endswith("膜")


def _relevance(title: str, kw: str) -> float:
    """借用包里的打分：实测它给真·小米15 打 1.00、给堆关键词的 Redmi Note 15 打 0.50，
    比我自己写的字符串匹配可靠。取不到就退回本地匹配规则。"""
    try:
        import best_price_mcp
        return float(best_price_mcp._relevance_score(title, kw))
    except Exception:
        return 1.0 if _matches(title, kw) else 0.0


def _model_ok(title: str, kw: str) -> bool:
    try:
        import best_price_mcp
        return bool(best_price_mcp._model_number_matches(title, kw))
    except Exception:
        return True


def _pick(items: list, kw: str) -> tuple:
    """从候选里挑本体：先按相关性、再按价格。

    顺序很重要——只按价格排会把 ¥16.6 的收纳包排到 ¥2548 的真机前面，
    这正是包自己踩过的坑（它把收纳包当最低价推荐给我们）。
    """
    want_accessory = any(a in _norm(kw) for a in _ACCESSORY)
    scored, rest = [], []
    for raw in items:
        title = (raw or {}).get("name") or ""
        # 用户本来就是来比一张贴膜/一个壳的价时，不能把它当配件滤掉
        if not want_accessory and _is_accessory(title):
            rest.append(raw)
            continue
        rel = _relevance(title, kw)
        if not _model_ok(title, kw) or rel < MIN_RELEVANCE:
            rest.append(raw)
            continue
        price = _num((raw or {}).get("final_price")) or _num((raw or {}).get("price")) or 10 ** 9
        scored.append((rel, price, raw))
    if not scored:
        if rest and not want_accessory and all(_is_accessory((r or {}).get("name")) for r in rest):
            return None, [], "只搜到配件和周边，没有找到整机本体（该型号可能不在数据源里）"
        return None, [], "没有匹配到该型号的商品"
    scored.sort(key=lambda x: (-x[0], x[1]))
    # 只留和最高分同一档的：小米15(1.00) 和混进来的 Redmi Note 15(0.50) 就此分开，
    # 而用户单纯来比一张钢化膜(整批最高 0.50)时也不会被清空
    top = scored[0][0]
    hit = [s[2] for s in scored if s[0] >= top - REL_BAND]
    best = hit[0]
    note = ""
    prices = [_num((r or {}).get("final_price")) or _num((r or {}).get("price")) or 0 for r in hit]
    low, mid = min(prices), sorted(prices)[len(prices) // 2]
    if len(prices) >= 3 and mid and low and mid / low >= _SUSPECT_RATIO:
        note = "最低价 ¥%s 与其余档位（中位 ¥%s）差得离谱，可能是配件或不同型号，下单前核对店铺与规格" % (
            low, mid)
    return best, hit[1:3], note


def _gather(ex, platforms: tuple, kw: str) -> list:
    """同一个关键词下并发查多平台，按 platforms 的固定顺序返回，输出次序因此是确定的。

    只在「同一个关键词内」并行：跨关键词仍然保持 search() 里查到就停的写法，
    否则一次比价会把共享日配额按关键词个数翻倍花掉。
    """
    futures = [(p, ex.submit(_search_one, p, kw)) for p in platforms]
    out = []
    for p, fut in futures:
        try:
            rows, err = fut.result()
        except Exception as e:                 # _search_one 内部已 try，这里只兜线程/导入类意外
            log.exception("%s 比价线程异常", p)
            rows, err = [], str(e)[:120]
        out.append((p, rows, err))
    return out


def search(keyword: str, limit: int = 6) -> tuple:
    """按商品名比价。返回 (items, warnings)，取不到数据时 items 为空、warnings 说明原因。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return [], ["没有可比价的商品名"]
    try:
        import best_price_mcp
    except Exception:
        log.exception("best-price-mcp 导入失败")
        return [], ["比价模块不可用（best-price-mcp 导入失败），只能给各平台搜索入口"]
    try:
        best_price_mcp.PROXY_TIMEOUT = _CONNECT_TIMEOUT
    except Exception:
        pass

    items, warnings, notes = [], [], []
    platforms = ("jd", "taobao")
    # 串行时两个平台的超时是相加的，京东被限流卡满 8 秒时天猫也得排队；并发后取最大值
    with ThreadPoolExecutor(max_workers=len(platforms), thread_name_prefix="price") as ex:
        for kw in _candidates(keyword):
            for platform, rows, err in _gather(ex, platforms, kw):
                if err:
                    warnings.append("%s接口：%s" % (PLATFORM_NAMES[platform], err))
                    continue
                if not rows:
                    continue
                best, alts, note = _pick(rows, kw)
                if note:
                    notes.append("%s：%s" % (PLATFORM_NAMES[platform], note))
                if best:
                    items.append(_item(platform, best))
                    for a in alts:
                        items.append(_item(platform, a))
            if items:
                break                        # 有结果就别再打第二个关键词，省共享配额
    if not items:
        cands = _candidates(keyword)
        uniq = []
        for w in warnings + notes:
            if w and w not in uniq:
                uniq.append(w)
        miss = "；".join(uniq) or "两个平台都没有返回这个商品"
        return [], [miss + "（实际用于搜索的词：%s）" % (cands[0] or keyword)[:30]]
    items.sort(key=lambda x: x.get("final_price") or 10 ** 9)
    return items[:max(1, int(limit))], sorted(set(warnings + notes) - {""})
