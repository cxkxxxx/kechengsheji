"""部署环境数据库初始化：AI 应用四张表（幂等，可重复执行）。

为什么需要这个脚本：
- 开发库的表是后端启动时 Base.metadata.create_all() 自动建的；
- 但 create_all 只「建缺失的表」，不保证所有部署环境都会走到这一步
  （比如先手工建库再启动、或用了只读账号、或多实例部署时只有第一个实例建表）；
- AI 应用上线依赖 ai_creations / ai_bill_reports / ai_exec_plans / ai_reviews
  四张表，缺任何一张对应接口直接 500。

用法（部署机上，先配好 .env 里的 DATABASE_URL）：
    cd backend
    python migrate_ai_tables.py

脚本可重复执行：每张表先查 information_schema，存在就跳过。
表结构与 app/models/ai_assist.py 一一对应，改动模型后要同步改这里。
"""
import sys

from sqlalchemy import text

from app.core.database import engine

TABLES = {
    "ai_creations": """
        CREATE TABLE ai_creations (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            scene VARCHAR(20) NULL,
            mode VARCHAR(20) NULL,
            input_json TEXT NULL,
            output_json TEXT NULL,
            article_id INT NULL,
            model VARCHAR(40) NULL,
            created_at DATETIME NULL,
            PRIMARY KEY (id),
            KEY ix_ai_creations_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "ai_bill_reports": """
        CREATE TABLE ai_bill_reports (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            month VARCHAR(7) NOT NULL,
            stats_json TEXT NULL,
            report_json TEXT NULL,
            model VARCHAR(40) NULL,
            created_at DATETIME NULL,
            PRIMARY KEY (id),
            KEY ix_ai_bill_reports_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "ai_exec_plans": """
        CREATE TABLE ai_exec_plans (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            article_id INT NULL,
            title VARCHAR(200) NULL,
            plan_json TEXT NULL,
            est_saving FLOAT NULL,
            actual_saving FLOAT NULL,
            status VARCHAR(20) NULL,
            model VARCHAR(40) NULL,
            created_at DATETIME NULL,
            updated_at DATETIME NULL,
            PRIMARY KEY (id),
            KEY ix_ai_exec_plans_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "ai_reviews": """
        CREATE TABLE ai_reviews (
            id INT NOT NULL AUTO_INCREMENT,
            target_type VARCHAR(10) NOT NULL,
            target_id INT NOT NULL,
            result_json TEXT NULL,
            model VARCHAR(40) NULL,
            admin_id INT NULL,
            created_at DATETIME NULL,
            PRIMARY KEY (id),
            KEY ix_ai_reviews_target_id (target_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def main():
    created, skipped = [], []
    with engine.begin() as conn:
        for name, ddl in TABLES.items():
            exists = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = :t"),
                {"t": name}).scalar() > 0
            if exists:
                skipped.append(name)
            else:
                conn.execute(text(ddl))
                created.append(name)
    if created:
        print("created tables: " + ", ".join(created))
    if skipped:
        print("already exist (skipped): " + ", ".join(skipped))
    if not created and not skipped:
        print("nothing to do")
    print("ai tables migration done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
