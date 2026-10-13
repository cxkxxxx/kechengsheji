"""给缺少封面的攻略 / 帖子生成内容相关封面图并回填数据库。

在 backend 目录下运行：

    python scripts/gen_covers.py            # 只补没有图的
    python scripts/gen_covers.py --force    # 全部重新生成

只用于演示 / 展示数据。用户自己在小程序里发帖传图走 /upload/image，不会碰到这里。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.article import Article          # noqa: E402
from app.models.post import Post                # noqa: E402
from app.core.config import UPLOAD_DIR          # noqa: E402
from app.core.database import SessionLocal      # noqa: E402
from app.utils import covers                    # noqa: E402

# 必须落在 UPLOAD_DIR 底下：main.py 把 /static 挂到的是 static/uploads，
# 放 static/covers 的话 URL /static/covers/x.jpg 会 404。
OUT_DIR = os.path.join(UPLOAD_DIR, "covers")


def main():
    ap = argparse.ArgumentParser(description="生成展示用封面图")
    ap.add_argument("--force", action="store_true", help="已有封面的也重新生成")
    args = ap.parse_args()

    if not covers.font_path():
        print("没找到中文字体，生成出来中文会是豆腐块。装一个微软雅黑/文泉驿/PingFang 再跑。")
        return 1

    db = SessionLocal()
    made = 0
    try:
        arts = db.query(Article).all()
        for a in arts:
            if a.cover and not args.force:
                continue
            covers.write(a.title, OUT_DIR, badge=a.category or "攻略")
            a.cover = covers.static_url(a.title)
            made += 1

        posts = db.query(Post).all()
        for p in posts:
            has = bool(p.images) and p.images not in ("[]", "null")
            if has and not args.force:
                continue
            first = (p.tags or "社区").split(",")[0].strip() or "社区"
            covers.write(p.title, OUT_DIR, badge=first)
            p.images = json.dumps([covers.static_url(p.title)], ensure_ascii=False)
            made += 1

        db.commit()
        files = os.listdir(OUT_DIR) if os.path.isdir(OUT_DIR) else []
        total_kb = sum(os.path.getsize(os.path.join(OUT_DIR, f)) for f in files) / 1024
        print("回填 %d 条；目录 %s 共 %d 张、%.0fKB（单张上限 %.0fKB）"
              % (made, OUT_DIR, len(files), total_kb, covers.COVER_MAX_BYTES / 1024))
        print("小程序里 <image> 要绝对地址，前端会用 baseUrl 拼 /static/covers/xxx.jpg")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
