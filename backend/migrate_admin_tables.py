"""管理后台升级的数据库迁移（幂等，可重复执行）。

两件事：
1. users 加 status 列（active/disabled/deleted）。管理端「停用/软删除」靠它，
   不做级联物理删除，保住帖子/账单等业务关联。
2. 建 admin_logs 操作日志表（管理端写操作留痕）。

用法（先配好 .env 的 DATABASE_URL）：
    cd backend
    python migrate_admin_tables.py

create_all 只建缺失的表、不会给已有表加列，所以 users.status 必须在这里 ALTER。
"""
import sys

from sqlalchemy import text

from app.core.database import engine

ADMIN_LOGS_DDL = """
    CREATE TABLE admin_logs (
        id INT NOT NULL AUTO_INCREMENT,
        admin_id INT NOT NULL,
        admin_name VARCHAR(50) NULL,
        action VARCHAR(40) NOT NULL,
        target_type VARCHAR(30) NULL,
        target_id INT NULL,
        detail VARCHAR(300) NULL,
        created_at DATETIME NULL,
        PRIMARY KEY (id),
        KEY ix_admin_logs_admin_id (admin_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def main():
    with engine.begin() as conn:
        has_status = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'status'"
        )).scalar() > 0
        if has_status:
            print("users.status already exists (skipped)")
        else:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))
            print("users.status added")

        has_logs = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'admin_logs'"
        )).scalar() > 0
        if has_logs:
            print("admin_logs already exists (skipped)")
        else:
            conn.execute(text(ADMIN_LOGS_DDL))
            print("admin_logs created")
    print("admin tables migration done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
