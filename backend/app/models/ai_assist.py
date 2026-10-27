"""AI 应用功能的落库表。四张表对应四个 AI 场景，全部保留原始输出，方便追溯。

设计原则：
- AI 生成的内容永远存 JSON 原文 + 结构化结果两份口径里的一份（这里存结构化 JSON 串），
  模型升级后旧记录仍按当时的形状展示；
- AI 生成 ≠ 用户确认：执行计划的「实际节省」不走这些表，仍写 checkins（唯一省钱口径）。
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from app.core.database import Base


class AICreation(Base):
    """AI 创作助手的历史：用户输入 → 模型输出，发布与否由用户决定。"""
    __tablename__ = "ai_creations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    scene = Column(String(20), default="article")          # article / post
    mode = Column(String(20), default="generate")          # generate/title/polish/reorganize
    input_json = Column(Text)                              # 用户给的主题/经历/场景
    output_json = Column(Text)                             # 模型结构化输出（已校验）
    article_id = Column(Integer, default=0)                # 用这份草稿正式发布后回填
    model = Column(String(40), default="")                 # 生成时用的模型名
    created_at = Column(DateTime, server_default=func.now())


class AIBillReport(Base):
    """AI 账单解读报告：统计数字由程序算好存档，AI 只写解读，历史可回看。"""
    __tablename__ = "ai_bill_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    month = Column(String(7), nullable=False)              # YYYY-MM
    stats_json = Column(Text)                              # 程序计算的统计快照
    report_json = Column(Text)                             # AI 解读（summary/points/advice）
    model = Column(String(40), default="")
    created_at = Column(DateTime, server_default=func.now())


class AIExecPlan(Base):
    """攻略执行计划：步骤勾选、清单实买金额都存在 plan_json 里，整包更新。

    actual_saving 只是这份计划的展示镜像；真正进省钱统计的是 checkins 表
    （确认时由服务端写入，source=攻略），两处由 confirm 接口保证一致。
    """
    __tablename__ = "ai_exec_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    article_id = Column(Integer, default=0)                # 来源攻略
    title = Column(String(200), default="")                # 计划标题（来自攻略标题）
    plan_json = Column(Text)                               # steps/shopping/prep/cautions/advice
    est_saving = Column(Float, default=0)                  # AI 预计可省（仅供参考，绝不算成果）
    actual_saving = Column(Float, default=0)               # 用户确认的实际节省（镜像）
    status = Column(String(20), default="进行中")           # 进行中 / 已完成
    model = Column(String(40), default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class AIReview(Base):
    """AI 审核辅助记录：只给管理员参考，最终审核决定权在管理员。"""
    __tablename__ = "ai_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_type = Column(String(10), nullable=False)       # article / post
    target_id = Column(Integer, nullable=False, index=True)
    result_json = Column(Text)                             # 风险标签/质量建议/是否需人工复核
    model = Column(String(40), default="")
    admin_id = Column(Integer, default=0)                  # 触发分析的管理员
    created_at = Column(DateTime, server_default=func.now())
