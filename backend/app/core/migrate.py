from sqlalchemy import text

from app.core.database import engine

# create_all() 只建新表，不会给已存在的表补新列，所以后加的列在这里补一次。
# 表名/列名都是代码里的常量，不来自请求参数。
_PENDING_COLUMNS = [
    ("chat_records", "agent", "VARCHAR(20) DEFAULT 'default'"),
    ("chat_records", "links", "TEXT"),
    ("chat_records", "tables", "TEXT"),
    # 开放用户投稿攻略。status 给存量行回填 approved，否则老数据会在列表里集体消失
    ("articles", "images", "TEXT"),
    ("articles", "user_id", "INT DEFAULT 0"),
    ("articles", "status", "VARCHAR(20) DEFAULT 'approved'"),
    # 月度支出上限：和「省多少」是两种目标，允许同时设
    ("budget_plans", "spend_limit", "FLOAT DEFAULT 0"),
    # 昵称+密码登录。原来 register 把哈希算出来就扔了，库里没这列所以永远登不回去
    ("users", "password_hash", "VARCHAR(120)"),
    # 账单明细：支付平台和交易单号。手打的账可以留空，拍照/导入的账单才有
    ("bills", "pay_channel", "VARCHAR(30)"),
    ("bills", "order_no", "VARCHAR(64)"),
]

# 补列后需要把存量 NULL 回填成空串的 (表, 列)
_BACKFILL_EMPTY = [
    ("bills", "pay_channel"),
    ("bills", "order_no"),
]


def ensure_columns() -> list:
    """幂等地补齐后加列，返回本次真正加上的列名。"""
    added = []
    with engine.begin() as conn:
        for table, column, ddl in _PENDING_COLUMNS:
            found = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).first()
            if found:
                continue
            conn.execute(text("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, ddl)))
            added.append("%s.%s" % (table, column))
        # 补列之后存量行全是 NULL，而接口按 str 返回。回填成空串，否则每读一行都得靠
        # schema 兜底 —— 回填前 GET /bills 直接 500，账单页整个打不开。
        for table, column in _BACKFILL_EMPTY:
            conn.execute(text("UPDATE %s SET %s = '' WHERE %s IS NULL"
                              % (table, column, column)))
    return added
