"""生成毕业设计数据库设计说明（从真实 MySQL introspect，保证与库一致）。

用法：cd backend && python scripts/gen_db_doc.py
输出：backend/数据库设计说明.md
"""
import sys
from datetime import date

sys.path.insert(0, ".")
from sqlalchemy import inspect
from app.core.database import engine

DESC = {
 "users": {"id": "主键", "openid": "微信 openid（唯一）", "nickname": "昵称", "avatar": "头像 URL",
           "password_hash": "昵称密码登录的 bcrypt 哈希", "budget_goal": "月度省钱目标(元)",
           "total_saved": "累计已省(元)", "status": "账号状态 active/disabled/deleted", "created_at": "注册时间"},
 "admins": {"id": "主键", "username": "管理员账号(唯一)", "password_hash": "密码哈希", "created_at": "创建时间"},
 "admin_logs": {"id": "主键", "admin_id": "操作管理员", "admin_name": "管理员账号快照", "action": "动作 create/update/delete/status",
                "target_type": "对象类型", "target_id": "对象 ID", "detail": "一句话说明", "created_at": "操作时间"},
 "articles": {"id": "主键", "title": "标题", "content": "正文(Markdown)", "category": "分类", "cover": "封面 URL",
              "images": "配图 JSON 数组", "author": "作者", "user_id": "投稿人(0=管理端)", "status": "pending/approved/rejected",
              "likes": "点赞数", "views": "浏览量", "created_at": "创建时间"},
 "posts": {"id": "主键", "user_id": "发帖人", "title": "标题", "content": "正文", "images": "图片 JSON", "tags": "标签(逗号分隔)",
           "status": "pending/approved/rejected", "likes": "点赞数", "comments_count": "评论数", "created_at": "创建时间"},
 "comments": {"id": "主键", "user_id": "评论者", "target_type": "article/post", "target_id": "目标 ID", "content": "评论内容",
              "parent_id": "父评论(0=一级)", "created_at": "创建时间"},
 "post_likes": {"id": "主键", "user_id": "点赞用户", "post_id": "帖子", "created_at": "点赞时间"},
 "favorites": {"id": "主键", "user_id": "收藏用户", "target_type": "article/post", "target_id": "目标 ID", "created_at": "收藏时间"},
 "bills": {"id": "主键", "user_id": "用户", "amount": "金额(元)", "category": "消费分类", "source": "用途备注",
           "pay_channel": "支付平台", "order_no": "交易单号", "bill_date": "消费日期", "ocr_raw": "OCR 原始数据", "created_at": "创建时间"},
 "budget_plans": {"id": "主键", "user_id": "用户", "month": "月份 YYYY-MM", "target_amount": "省钱目标", "spend_limit": "支出上限",
                  "saved_amount": "已省(由 checkins 重算)", "checkin_days": "打卡天数", "last_checkin_date": "最近打卡"},
 "checkins": {"id": "主键", "user_id": "用户", "day": "记录日期", "saved_amount": "本笔实际节省", "note": "备注",
              "source": "打卡/攻略/社区经验/AI方案", "ref_type": "关联类型", "ref_id": "关联内容 ID", "created_at": "创建时间"},
 "price_histories": {"id": "主键", "product_name": "商品名", "price": "价格", "platform": "平台", "url": "商品链接", "recorded_at": "记录时间"},
 "coupon_activities": {"id": "主键", "title": "活动标题", "content": "详情", "platform": "平台", "deadline": "截止时间",
                       "verified": "是否已验证", "created_at": "创建时间"},
 "chat_records": {"id": "主键", "user_id": "用户", "role": "user/assistant/tool", "content": "消息内容", "tool_calls": "工具调用 JSON",
                  "links": "跳转卡片 JSON", "tables": "表格 JSON", "agent": "coupon/budget", "tokens_used": "消耗 token", "created_at": "创建时间"},
 "ai_creations": {"id": "主键", "user_id": "用户", "scene": "article/post", "mode": "generate/title/polish/reorganize",
                  "input_json": "用户输入", "output_json": "模型结构化输出", "article_id": "发布后回填的攻略", "model": "模型名", "created_at": "创建时间"},
 "ai_bill_reports": {"id": "主键", "user_id": "用户", "month": "报告月份", "stats_json": "程序统计快照", "report_json": "AI 解读",
                     "model": "模型名", "created_at": "生成时间"},
 "ai_exec_plans": {"id": "主键", "user_id": "用户", "article_id": "来源攻略", "title": "计划标题", "plan_json": "步骤/清单 JSON",
                   "est_saving": "AI 预计可省(仅参考)", "actual_saving": "用户确认实际节省(镜像)", "status": "进行中/已完成",
                   "model": "模型名", "created_at": "创建时间", "updated_at": "更新时间"},
 "ai_reviews": {"id": "主键", "target_type": "article/post", "target_id": "审核对象", "result_json": "AI 风险/质量意见",
                "model": "模型名", "admin_id": "触发管理员", "created_at": "分析时间"},
}

PURPOSE = {
 "users": "小程序用户", "admins": "管理端账号", "admin_logs": "管理操作留痕", "articles": "省钱攻略",
 "posts": "社区帖子", "comments": "评论", "post_likes": "帖子点赞", "favorites": "收藏",
 "bills": "消费账单", "budget_plans": "月度预算/省钱目标", "checkins": "实际节省记录",
 "price_histories": "商品历史报价", "coupon_activities": "优惠活动", "chat_records": "AI 对话历史",
 "ai_creations": "AI 创作记录", "ai_bill_reports": "AI 账单报告", "ai_exec_plans": "AI 执行计划", "ai_reviews": "AI 审核辅助",
}

LOGICAL_FK = [
 ("articles", "user_id", "users", "id", "投稿人(0=官方)"),
 ("posts", "user_id", "users", "id", "发帖人"),
 ("comments", "user_id", "users", "id", "评论者"),
 ("comments", "target_id", "articles/posts", "id", "按 target_type 指向"),
 ("post_likes", "user_id", "users", "id", ""), ("post_likes", "post_id", "posts", "id", ""),
 ("favorites", "user_id", "users", "id", ""), ("favorites", "target_id", "articles/posts", "id", "按 target_type"),
 ("bills", "user_id", "users", "id", ""), ("budget_plans", "user_id", "users", "id", ""),
 ("checkins", "user_id", "users", "id", ""), ("checkins", "ref_id", "articles/posts", "id", "按 ref_type"),
 ("chat_records", "user_id", "users", "id", ""),
 ("ai_creations", "user_id", "users", "id", ""), ("ai_creations", "article_id", "articles", "id", "发布回填"),
 ("ai_bill_reports", "user_id", "users", "id", ""),
 ("ai_exec_plans", "user_id", "users", "id", ""), ("ai_exec_plans", "article_id", "articles", "id", ""),
 ("ai_reviews", "target_id", "articles/posts", "id", "按 target_type"), ("ai_reviews", "admin_id", "admins", "id", ""),
 ("admin_logs", "admin_id", "admins", "id", ""),
]


def main():
    ins = inspect(engine)
    tables = sorted(ins.get_table_names())
    out = []
    out.append("# 省钱攻略 · 数据库设计说明\n")
    out.append("> 生成日期 %s；由 `scripts/gen_db_doc.py` 从真实 MySQL introspect 生成，与库结构一致。\n" % date.today())
    out.append("## 一、表清单（共 %d 张关系表）\n" % len(tables))
    out.append("| 表 | 用途 | 字段数 | 主键 |\n|---|---|---|---|")
    for t in tables:
        pk = ins.get_pk_constraint(t)["constrained_columns"]
        out.append("| %s | %s | %d | %s |" % (t, PURPOSE.get(t, ""), len(ins.get_columns(t)), ",".join(pk)))
    out.append("\nChromaDB 向量库（攻略知识检索）不计入关系表。\n")

    out.append("## 二、字段说明\n")
    for t in tables:
        out.append("### %s（%s）\n" % (t, PURPOSE.get(t, "")))
        out.append("| 字段 | 类型 | 可空 | 键 | 说明 |\n|---|---|---|---|---|")
        pk = ins.get_pk_constraint(t)["constrained_columns"]
        idx = {i["name"]: i for i in ins.get_indexes(t)}
        for c in ins.get_columns(t):
            key = "PK" if c["name"] in pk else ("IDX" if any(c["name"] in i["column_names"] for i in idx.values()) else "")
            out.append("| %s | %s | %s | %s | %s |" % (
                c["name"], str(c["type"]), "YES" if c["nullable"] else "NO", key,
                DESC.get(t, {}).get(c["name"], "")))
        out.append("")

    out.append("## 三、主键与外键说明\n")
    out.append("- 所有表主键均为 `id`（INT 自增）。\n")
    out.append("- 本项目**未建物理外键约束**（MySQL 层 FK 为空），表间关联通过业务字段（`user_id`/`target_id`/`post_id` 等）在应用层维护，删除时由业务代码处理关联（用户删除为软删除，保留业务数据）。逻辑外键如下：\n")
    out.append("| 子表.字段 | 指向 | 说明 |\n|---|---|---|")
    for ct, cc, pt, pc, note in LOGICAL_FK:
        out.append("| %s.%s | %s.%s | %s |" % (ct, cc, pt, pc, note))
    out.append("")

    out.append("## 四、E-R 图\n")
    out.append("```mermaid\nerDiagram")
    rel = [
        ("users", "posts", "1对多"), ("users", "bills", "1对多"), ("users", "budget_plans", "1对多"),
        ("users", "checkins", "1对多"), ("users", "comments", "1对多"), ("users", "favorites", "1对多"),
        ("users", "post_likes", "1对多"), ("users", "chat_records", "1对多"), ("users", "ai_creations", "1对多"),
        ("users", "ai_bill_reports", "1对多"), ("users", "ai_exec_plans", "1对多"),
        ("posts", "comments", "1对多"), ("posts", "post_likes", "1对多"),
        ("articles", "comments", "1对多"), ("articles", "ai_exec_plans", "1对多"),
        ("admins", "ai_reviews", "1对多"), ("admins", "admin_logs", "1对多"),
    ]
    for a, b, card in rel:
        out.append("    %s ||--o{ %s : \"%s\"" % (a, b, card))
    out.append("```\n")

    out.append("## 五、核心 CRUD 接口清单\n")
    out.append("| 实体 | 创建 | 查询 | 修改 | 删除 |\n|---|---|---|---|---|")
    crud = [
        ("用户(管理)", "小程序注册 /auth/register", "GET /admin/api/users", "PATCH /admin/api/users/{id}", "DELETE /admin/api/users/{id}(软删除)"),
        ("管理员", "POST /admin/api/admins", "GET /admin/api/admins", "PATCH /admin/api/admins/{id}/password", "DELETE /admin/api/admins/{id}"),
        ("攻略", "POST /admin/api/articles", "GET /admin/api/articles", "PUT /admin/api/articles/{id}", "DELETE /admin/api/articles/{id}"),
        ("帖子", "POST /admin/api/posts", "GET /admin/api/posts", "PUT /admin/api/posts/{id}", "DELETE /admin/api/posts/{id}"),
        ("评论", "小程序 /comments", "GET /admin/api/comments", "-", "DELETE /admin/api/comments/{id} / batch-delete"),
        ("报价", "POST /admin/api/prices", "GET /admin/api/prices", "PUT /admin/api/prices/{id}", "DELETE /admin/api/prices/{id}"),
        ("活动", "POST /admin/api/coupons", "GET /admin/api/coupons", "PUT /admin/api/coupons/{id}", "DELETE /admin/api/coupons/{id}"),
        ("账单(用户端)", "POST /bills", "GET /bills", "PUT /bills/{id}", "DELETE /bills/{id}"),
    ]
    for row in crud:
        out.append("| " + " | ".join(row) + " |")
    out.append("\n审核状态：PATCH /admin/api/articles/{id}/status、/admin/api/posts/{id}/status；AI 辅助：POST /admin/api/ai-review（仅参考，不替代人工）。\n")

    out.append("## 六、初始化与迁移\n")
    out.append("1. 配好 `backend/.env` 的 `DATABASE_URL`。\n")
    out.append("2. 启动后端时 `Base.metadata.create_all()` 自动建缺失的表。\n")
    out.append("3. 增量迁移脚本（幂等）：`python migrate_ai_tables.py`（AI 四表）、`python migrate_checkin_records.py`（省钱记录）、`python migrate_admin_tables.py`（users.status + admin_logs）。\n")
    out.append("4. 演示数据：`python scripts/seed_demo_months.py`（只补空月份，不删已有）。\n")

    path = "数据库设计说明.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("written", path, "tables:", len(tables))


if __name__ == "__main__":
    main()
