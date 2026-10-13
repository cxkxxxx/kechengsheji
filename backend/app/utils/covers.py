"""按标题/分类生成展示用封面图。

只给 seed 演示数据用（用户真实发帖是自己上传，不走这里）。
之所以服务端画而不是调文生图：演示图要的是「稳定、秒出、体积可控」，
AI 出图每张几秒、要额度、中文还会画错字。

配色和图形都从标题关键词推出来，所以同一批数据每次生成的图是一致的。
"""
import hashlib
import os
import re

from PIL import Image, ImageDraw, ImageFont

# 输出尺寸与体积目标：900x500 够首页大图用，压到 80KB 以内免得拖慢小程序
COVER_W = 900
COVER_H = 500
COVER_MAX_BYTES = 80 * 1024

# 关键词 → (起色, 止色, 强调色)。
# 不用「先匹配到就赢」：那样「手机话费套餐」会被单字"餐"抢去配色。
# 改成按命中的关键词长度打分，越具体的词权重越高。
# 也别放"餐""买"这种单字，中文里到处都能撞上。
_PALETTE = [
    (("记账", "账单", "预算", "存钱", "回血"), ("#14B8A6", "#155E75", "#CCFBF1")),
    (("话费", "流量", "套餐", "运营商", "宽带"), ("#0EA5E9", "#4338CA", "#E0F2FE")),
    (("电费", "水电", "功耗", "取暖", "家电", "电器"), ("#F59E0B", "#B45309", "#FEF3C7")),
    (("奶茶", "咖啡", "外卖", "午餐", "晚餐", "早餐", "带饭", "三餐", "吃饭"), ("#F97316", "#DB2777", "#FFEDD5")),
    (("超市", "纸巾", "日用", "团购", "打折", "拼多多"), ("#10B981", "#0F766E", "#D1FAE5")),
    (("房租", "租房", "宿舍", "毕业"), ("#6366F1", "#312E81", "#E0E7FF")),
    (("衣柜", "断舍离", "买衣服", "鞋"), ("#8B5CF6", "#5B21B6", "#EDE9FE")),
    (("旅行", "穷游", "健身", "门票"), ("#F43F5E", "#9F1239", "#FFE4E6")),
    (("二手", "闲置", "捡漏"), ("#64748B", "#1E293B", "#E2E8F0")),
    (("羊毛", "薅", "优惠券", "0元", "免费", "陷阱"), ("#EAB308", "#B45309", "#FEF9C3")),
    (("数码", "淘宝", "京东", "比价", "大促", "网购"), ("#3B82F6", "#1E3A8A", "#DBEAFE")),
    (("宠物", "养猫", "养狗", "猫粮", "狗粮"), ("#A855F7", "#6B21A8", "#F3E8FF")),
]
_DEFAULT = ("#4433E0", "#2F6BF0", "#EEF0FE")

# 系统里能拿到的中文字体，按优先级；找不到就退回 Pillow 自带（中文会变成豆腐块）
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def font_path():
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return ""


def palette_for(text: str) -> tuple:
    """按命中的关键词长度打分取配色，越具体的词权重越高。"""
    text = text or ""
    best, best_score = _DEFAULT, 0
    for words, colors in _PALETTE:
        score = sum(len(w) for w in words if w in text)
        if score > best_score:
            best, best_score = colors, score
    return best


def slug(text: str) -> str:
    """标题定长哈希做文件名：中文直接当文件名在部分服务器上会出问题。"""
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()[:12]


def static_url(text: str) -> str:
    return "/static/covers/%s.jpg" % slug(text)


def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _gradient(w: int, h: int, c1: tuple, c2: tuple) -> Image.Image:
    """对角渐变。逐行插值再旋转，比逐像素快一个数量级。"""
    base = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(base)
    for x in range(w):
        t = x / max(w - 1, 1)
        d.line([(x, 0), (x, h)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return base


def _wrap(draw, text: str, font, max_w: int, max_lines: int = 3) -> list:
    """按字宽折行，中文没有空格所以逐字量。超出行数末尾加省略号。"""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
            continue
        lines.append(cur)
        cur = ch
        if len(lines) == max_lines:
            break
    if len(lines) == max_lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last + "…"
        return lines
    if cur:
        lines.append(cur)
    return lines


def render(title: str, badge: str = "") -> bytes:
    """生成一张封面，返回 JPEG 字节。"""
    c1, c2, accent = (_hex(x) for x in palette_for(title))
    img = _gradient(COVER_W, COVER_H, c1, c2)
    d = Draw = ImageDraw.Draw(img)   # noqa: F841  (Draw 别名给下面复用)

    # 柔光圆点：让纯色渐变不至于太平
    for cx, cy, r, a in ((760, 60, 220, 26), (60, 460, 180, 20), (500, 300, 300, 12)):
        layer = Image.new("RGB", (COVER_W, COVER_H), (0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
        img = Image.blend(img, layer, a / 255.0)
    d = ImageDraw.Draw(img)

    fp = font_path()
    f_badge = ImageFont.truetype(fp, 30) if fp else ImageFont.load_default()
    f_title = ImageFont.truetype(fp, 62) if fp else ImageFont.load_default()

    pad = 64
    if badge:
        bw = int(d.textlength(badge, font=f_badge))
        d.rounded_rectangle([pad, pad, pad + bw + 44, pad + 60], 30, fill=(255, 255, 255, 255))
        d.text((pad + 22, pad + 10), badge, font=f_badge, fill=c2)

    lines = _wrap(d, title or "", f_title, COVER_W - pad * 2, max_lines=3)
    top = pad + (84 if badge else 24)
    for i, line in enumerate(lines):
        # 先落一层半透明阴影，压在渐变上才有可读性
        d.text((pad + 3, top + i * 82 + 3), line, font=f_title, fill=(0, 0, 0, 90))
        d.text((pad, top + i * 82), line, font=f_title, fill=(255, 255, 255, 255))

    d.text((pad, COVER_H - pad - 34), "省活攻略", font=f_badge, fill=accent)

    # 体积控制：先试 q=82，超预算就逐级降质，还超就缩图
    for q in (82, 74, 66, 58):
        buf = _jpeg(img, q)
        if len(buf) <= COVER_MAX_BYTES:
            return buf
    scale = 0.82
    while scale > 0.55:
        small = img.resize((int(COVER_W * scale), int(COVER_H * scale)), Image.LANCZOS)
        buf = _jpeg(small, 58)
        if len(buf) <= COVER_MAX_BYTES:
            return buf
        scale -= 0.08
    return buf


def _jpeg(img, quality: int) -> bytes:
    import io
    b = io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=quality, optimize=True, progressive=True)
    return b.getvalue()


def write(title: str, out_dir: str, badge: str = "") -> str:
    """生成并落盘，返回写出的文件名。"""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(title) + ".jpg")
    with open(path, "wb") as f:
        f.write(render(title, badge))
    return path
