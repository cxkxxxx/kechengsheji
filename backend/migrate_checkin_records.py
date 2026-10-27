"""一次性迁移：checkins 表从「一人一天一条」升级为通用省钱记录。

改动内容：
1. 去掉 (user_id, day) 唯一约束 uq_checkin_user_day —— 按攻略/AI 方案记的省钱
   和每日打卡可能同天多笔；
2. 加 source / ref_type / ref_id 三列，记录这笔省钱从哪来、关联哪条内容。

旧数据兼容：存量行保持原语义（就是每日打卡），source 由 server_default 补成「打卡」，
ref_type/ref_id 置空。budget_plans.saved_amount 本来就是明细重算的，不受影响。

脚本可重复执行：每一步都先查 information_schema 再动手。
"""
import sys

from sqlalchemy import text

from app.core.database import engine


def column_exists(conn, table: str, column: str) -> bool:
    return conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"),
        {"t": table, "c": column}).scalar() > 0


def index_exists(conn, table: str, index: str) -> bool:
    return conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"),
        {"t": table, "i": index}).scalar() > 0


def main():
    with engine.begin() as conn:
        if not column_exists(conn, "checkins", "source"):
            conn.execute(text(
                "ALTER TABLE checkins ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT '打卡'"))
            print("added column: source")
        if not column_exists(conn, "checkins", "ref_type"):
            conn.execute(text(
                "ALTER TABLE checkins ADD COLUMN ref_type VARCHAR(20) NOT NULL DEFAULT ''"))
            print("added column: ref_type")
        if not column_exists(conn, "checkins", "ref_id"):
            conn.execute(text(
                "ALTER TABLE checkins ADD COLUMN ref_id INT NULL"))
            print("added column: ref_id")
        if index_exists(conn, "checkins", "uq_checkin_user_day"):
            conn.execute(text("ALTER TABLE checkins DROP INDEX uq_checkin_user_day"))
            print("dropped unique constraint: uq_checkin_user_day")
    print("migration done")


if __name__ == "__main__":
    sys.exit(main())
