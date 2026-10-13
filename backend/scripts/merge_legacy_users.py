"""把旧 dev_ 登录遗留账号的内容并到一个账号上。

背景：修好之前 `openid = f"dev_{code[:16]}"`，wx.login 每次 code 都不同，
所以每登录一次就新建一个用户，帖子散落在十几个一次性账号里。
登录已经修好了，但历史内容还搁在那边，这个脚本负责搬回来。

在 backend 目录下运行：

    python scripts/merge_legacy_users.py --to 47            # 先看清单，不改数据
    python scripts/merge_legacy_users.py --to 47 --apply    # 确认后再真改

只搬 openid 以 dev_ 开头的遗留账号，seed 演示用户（openid 为 NULL）不动。
"""
import argparse
import sys

from sqlalchemy import func

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from app.core.database import SessionLocal           # noqa: E402
from app.models.bill import Bill                     # noqa: E402
from app.models.chat_record import ChatRecord        # noqa: E402
from app.models.comment import Comment               # noqa: E402
from app.models.favorite import Favorite             # noqa: E402
from app.models.post import Post                     # noqa: E402
from app.models.post_like import PostLike            # noqa: E402
from app.models.user import User                     # noqa: E402

# 默认只搬「我的」页面上看得见的社交内容。
# 账单和聊天记录千万别默认合：seed 给每个演示账号各造了 ~90 条账单，
# 合到一个账号上会让账单页同一月份重复十几遍，分析结果全是错的。
DEFAULT_TABLES = [("帖子", Post), ("评论", Comment), ("收藏", Favorite)]
EXTRA_TABLES = [("账单", Bill), ("点赞", PostLike), ("聊天记录", ChatRecord)]


def _count(db, model, uid):
    return db.query(func.count()).select_from(model).filter(model.user_id == uid).scalar() or 0


def main():
    ap = argparse.ArgumentParser(description="合并遗留 dev_ 账号的内容")
    ap.add_argument("--to", type=int, required=True, help="目标用户 id（保留的那个账号）")
    ap.add_argument("--apply", action="store_true", help="真正写库；不加就只打印清单")
    ap.add_argument("--all", action="store_true",
                    help="连账单/点赞/聊天记录一起搬（会把 seed 的演示账单堆到一个账号上，一般不要）")
    args = ap.parse_args()

    tables = (DEFAULT_TABLES + EXTRA_TABLES) if args.all else DEFAULT_TABLES

    db = SessionLocal()
    try:
        target = db.query(User).filter(User.id == args.to).first()
        if not target:
            print("找不到用户 id=%s" % args.to)
            return 1

        legacy = [u for u in db.query(User).filter(User.openid.like("dev\\_%")).all()
                  if u.id != target.id]
        if not legacy:
            print("没有 openid 以 dev_ 开头的遗留账号，无需合并。")
            return 0

        print("目标账号：id=%s 昵称=%s openid=%s" % (
            target.id, target.nickname, target.openid or "NULL"))
        print("搬迁范围：" + "、".join(k for k, _ in tables) + ("  <-- --all 全量" if args.all else ""))
        print("\n将被合并的遗留账号（%d 个）：" % len(legacy))
        totals = {label: 0 for label, _ in tables}
        for u in legacy:
            row = {label: _count(db, m, u.id) for label, m in tables}
            for k, v in row.items():
                totals[k] += v
            if any(row.values()):
                print("  id=%-4s %-12s %s  %s" % (
                    u.id, (u.nickname or "")[:12], (u.openid or "")[:26],
                    " ".join("%s=%d" % (k, v) for k, v in row.items() if v)))
        print("\n合计搬迁：" + "  ".join("%s=%d" % (k, v) for k, v in totals.items() if v))
        if not args.all:
            bills = sum(_count(db, Bill, u.id) for u in legacy)
            chats = sum(_count(db, ChatRecord, u.id) for u in legacy)
            print("（另有账单 %d 条、聊天记录 %d 条留在原账号未搬，加 --all 才会一起搬）" % (bills, chats))

        if not args.apply:
            print("\n这是预览，没有改任何数据。确认无误后加 --apply 执行。")
            return 0

        ids = [u.id for u in legacy]
        for label, m in tables:
            if m is PostLike:
                continue
            db.query(m).filter(m.user_id.in_(ids)).update({m.user_id: target.id},
                                                           synchronize_session=False)
        if args.all:
            # 同一条帖子可能被两个账号都点过赞，直接改属会撞唯一键，先删重复
            have = {p.post_id for p in db.query(PostLike).filter(PostLike.user_id == target.id).all()}
            if have:
                db.query(PostLike).filter(PostLike.user_id.in_(ids),
                                          PostLike.post_id.in_(list(have))).delete(
                    synchronize_session=False)
            db.query(PostLike).filter(PostLike.user_id.in_(ids)).update(
                {PostLike.user_id: target.id}, synchronize_session=False)
        for u in legacy:
            if args.all or not (_count(db, Bill, u.id) or _count(db, ChatRecord, u.id)):
                db.delete(u)     # 只剩空账号才敢删，否则留着它的账单
        db.commit()

        print("\n已合并。目标账号 id=%s 现在：帖子 %d 条、评论 %d 条、收藏 %d 条。" % (
            target.id, _count(db, Post, target.id), _count(db, Comment, target.id),
            _count(db, Favorite, target.id)))
        print("在小程序里退出重新登录（昵称密码），「我的发帖」就会显示这些。")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
