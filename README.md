# 省活攻略 · 基于大语言模型的省钱攻略智能推荐平台

> 微信小程序 **省活攻略** —— 一个会读你真实账单、能帮你记账的 AI 省钱助手。
> 除对话式 AI 助手外，还内置 AI 创作助手、AI 账单解读、AI 执行计划、AI 审核辅助四个应用场景，
> 贯穿「攻略 → 比价 → 执行 → 记实际省钱 → 分享」完整闭环。
> 详细部署与接口说明见 [使用手册.md](使用手册.md)。

## 它解决什么问题

记账类 App 只会告诉你「这个月花了多少」，不会告诉你**下个月怎么少花**。
这里把大模型接上了本地数据库：AI 回答省钱问题时会真的去查你的账单、你的省钱目标、
平台收录的优惠活动与比价记录，然后基于真实数字给建议；你也可以直接对它说
「昨晚外卖 18 块」，它就帮你把这笔账记上。

## 核心能力

| 能力 | 说明 |
|------|------|
| 2 个 AI 专家 | 优惠情报员（薅羊毛 / 比价 / 菜谱 / 攻略）· 理财管家（记账预算），各自独立上下文 |
| 12 个 Agent 工具 | Function Calling 自动选择，一轮问答最多连用 2 个，见下方工具表 |
| 流式对话 | SSE 逐字输出，支持上传图片让视觉模型看图 |
| 真实账单分析 | 总额、日均、分类占比、大额 TOP、上月环比、省钱目标达成 |
| 自然语言记账 | 一句话记多笔消费，回显每笔供核对 |
| 拍照记账 | 账单/支付截图发给 AI，识别金额、分类、支付渠道与交易单号后入账 |
| 月末支出预测 | 按已花金额推算月底总额，对照支出上限提前预警超支 |
| 固定扣费识别 | 从账单里揪出月月都在扣的订阅/水电，和积少成多的高频小额 |
| 月度省钱复盘 | 一段可直接发社区的月度总结，含环比、打卡、最值三笔 |
| 平替建议 | 针对打车/奶茶/外卖等高频消费给替代方案，按真实花费算可省金额 |
| 商品比价 | 独立比价页：贴商品链接或商品名，比京东/天猫到手价，查到价的才下发可点开的商品卡片 |
| 账单管理 | 按月查看、增删改、环形占比图、日历热力图、AI 建议、一键跳转 AI 分析 |
| 省钱记录 | 打卡/攻略/社区经验/AI 方案多来源记「实际节省」，补打卡、快捷记账，AI 预计值永不入账 |
| AI 创作助手 | 攻略/发帖页一键生成草稿：标题、摘要、正文、分类、标签、步骤；生成结果只是草稿，发布前必经用户修改 |
| AI 账单解读 | 程序算好月度统计，AI 只写解读；数据不足时必须明说；报告存档可回看、可追问 |
| AI 执行计划 | 攻略详情一键拆解成步骤清单 + 购物清单 + 预算建议，勾选进度、填实买金额、确认后真实节省才进统计 |
| AI 审核辅助 | 管理后台对待审内容给风险标签与质量建议，仅供参考，AI 不做任何自动封禁/驳回 |
| 内容社区 | 攻略文章、帖子、评论、点赞、收藏 |
| 管理后台 | `/admin` 可视化数据看板、内容审核与 AI 审查辅助 |

### AI 工具

| 工具 | 触发例子 | 数据来源 |
|------|---------|---------|
| `generate_recipe` | 「冰箱有西红柿和鸡蛋」 | 大模型生成 |
| `shopping_advice` | 「2000 元扫地机器人推荐」 | 大模型生成 |
| `search_knowledge` | 「外卖怎么点最省」 | 内置攻略 / ChromaDB RAG |
| `coupon_advice` | 「最近有什么羊毛」 | `coupon_activities` 表 |
| `price_compare` | 「哪个平台买便宜」/ 贴一条商品链接 | 京东·天猫实时到手价（best-price-mcp）+ `price_histories` 表 |
| `analyze_bills` | 「分析我这个月账单」 | `bills` + `budget_plans` 表 |
| `spending_forecast` | 「这个月会不会超支」「还能花多少」 | `bills` 日均 × 当月天数 + `budget_plans.spend_limit` |
| `detect_fixed_spend` | 「有没有我忘掉的扣费」 | `bills` 跨月聚合，只读本地、不接支付渠道 |
| `monthly_report` | 「帮我做个本月复盘」 | `bills` + `budget_plans`，含环比与打卡天数 |
| `cheaper_alternative` | 「打车花太多了有平替吗」 | `bills` 主题聚合 + 内置平替攻略 |
| `budget_advice` | 「我的省钱目标达成了吗」 | `budget_plans` + `bills` 表 |
| `add_bill` | 「昨晚外卖 18 块，记一下」 | 写入 `bills` 表 |

## 技术栈

微信小程序（原生）· FastAPI · SQLAlchemy · MySQL · 智谱 GLM（`glm-4-flash` 文本 / `glm-4v-flash` 视觉）· ChromaDB · JWT

大模型走 OpenAI 兼容协议，改 4 个环境变量即可换成阿里云 DashScope 等任意服务商。

## 30 秒跑起来

```bash
cd backend
copy .env.example .env        # 填入数据库密码与智谱 API Key
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后终端会打印四个入口，点开即用：

```
   后端接口      http://127.0.0.1:8000
   可视化接口文档 http://127.0.0.1:8000/docs      (Swagger，已中文化)
   可视化管理后台 http://127.0.0.1:8000/admin     (默认 admin/admin123)
   健康检查      http://127.0.0.1:8000/health
   真机/手机预览  http://192.168.x.x:8000
```

小程序侧：微信开发者工具导入 `frontend/`，勾选「不校验合法域名」，
`miniprogram/app.js` 的 `baseUrl` 指向后端地址（真机改成局域网 IP）。

完整步骤、演示数据导入、FAQ 见 [使用手册.md](使用手册.md)。

## 项目结构

```
backend/
├── app/
│   ├── main.py               # 入口：建表、补列、启动横幅、/health、中文化 Swagger
│   ├── core/
│   │   ├── config.py         # 全部配置来自 .env
│   │   ├── database.py       # SQLAlchemy 引擎与会话
│   │   ├── security.py       # JWT 鉴权
│   │   ├── rate_limit.py     # AI/登录接口限流（滑动窗口）
│   │   └── migrate.py        # 给已存在的表幂等补新列
│   ├── models/               # 17 张表（含 AI 应用 4 张：ai_creations / ai_bill_reports / ai_exec_plans / ai_reviews）
│   ├── schemas/              # Pydantic 出入参
│   ├── api/routes/           # 13 个模块 / 72 个接口方法
│   │   └── ai_assist.py      # AI 应用四场景：创作助手 / 账单解读 / 执行计划（confirm-saving 幂等）
│   ├── services/             # 比价编排：best_price 包装 / 链接解析 / price_service
│   ├── admin_web/            # 管理后台单页（含 AI 审查弹窗）
│   └── agent/                # AI 智能体
│       ├── engine.py         # 编排：多智能体注册表 + 工具调用 + 流式 + 图片转文字
│       ├── llm.py            # 大模型调用（流式/非流式/视觉自动切换与上限夹取）
│       ├── prompts.py        # AI 应用提示词按场景独立管理
│       ├── json_out.py       # 模型 JSON 输出统一解析/清洗，失败返回 502 让用户重试
│       ├── memory.py         # 对话记忆（按智能体隔离 + 字符预算）
│       └── tools/            # 12 个工具 + registry 自动注册
├── scripts/
│   ├── smoke_ai.py           # AI 应用四阶段冒烟（真实库 + 真实模型）
│   └── e2e_flows.py          # A/B/C/D 四条业务流端到端验证
├── tests/                    # 60 条 pytest（含 AI 接口归属隔离/幂等离线测试）
├── migrate_ai_tables.py      # 部署迁移：AI 四张表幂等建表
├── migrate_checkin_records.py    # 部署迁移：checkins 来源字段
├── .env.example              # 配置模板（.env 不入库）
└── requirements.txt

frontend/miniprogram/
├── app.wxss                  # 全站设计基座（CSS 变量 + 通用组件）
├── app.json                  # 页面与 tabBar
├── pages/                    # 12 个页面（5 个 tab + 7 个功能页，含比价页 / 执行计划页）
└── utils/request.js          # 统一请求：token、缓存、401 跳登录
```

页面自动化验证脚本在 `.auto-test/`（miniprogram-automator 连微信开发者工具，25 项点击/断言/截图），不属于运行时代码。

## 对话接口约定

小程序用 `POST /agent/chat`（SSE），每帧 `data: {...}`，`type` 四种：

```
data: {"type": "chunk", "text": "超市"}
data: {"type": "meta", "tool_used": "analyze_bills"}
data: {"type": "links", "items": [{"platform":"天猫","label":"小米山林奕心专卖店","url":"https://...","price":2860.0}]}
data: {"type": "done", "conversation_id": 123}
```

`links` 只在比价时出现，小程序渲染成平台卡片，点击复制该链接（微信小程序不能直接打开外部网址）。

两个容易踩的坑（本项目已处理，改动时别退回）：
- 收流式分块要用 `wx.request()` 返回的 `RequestTask.onChunkReceived()`，写在参数对象里不会触发。
- SSE 正文用 ASCII 转义（`json.dumps` 默认），中文原样上线时网络分块可能切在多字节中间导致乱码。

## 功能现状

已完成：后端 13 个模块 72 个接口方法、17 张表自动建表补列（部署可跑 `migrate_ai_tables.py` 显式初始化）、
JWT 鉴权、AI 智能体（多角色 + 12 工具 + 流式 + 图片 + 记忆隔离 + 限流）、AI 应用四件套
（创作助手 / 账单解读 / 执行计划 / 审核辅助，AI 生成与用户确认严格区分、实际节省唯一入账口）、
账单增删改与按月分析（支付渠道、交易单号、日历热力图、拍照记账）、省钱打卡与多来源省钱记录、
独立比价页、社区与收藏、管理后台（含 AI 审查辅助）、小程序 12 个页面与设计基座。

质量验证：pytest 60 条全过；A/B/C/D 四条业务流端到端 27 项全过（真实库 + 真实模型）；
小程序 12 页在微信开发者工具自动化验证 25/25 项（点击 / 断言 / 截图，脚本在 `.auto-test/`）。

待办：
- 微信正式登录（当前 `code` 直接映射 openid，注册密码未落库）
- 真机（手机）页面验证：当前自动化验证覆盖开发者工具模拟器，键盘遮挡与 rpx 真机适配待扫一遍
- 比价依赖 best-price-mcp 的第三方中转（共享日配额）：实测京东侧会整天返回「已达调用上限」，
  只剩天猫；要稳定就得换官方联盟 API，只需改 `app/services/best_price.py` 一个文件
- 文章点赞去重（已要求登录，但同一用户仍可重复 +1，需 `ArticleLike` 表）
- RAG 知识库语料导入（`data/chroma_db` 为空时走内置攻略兜底）
- 生产部署（HTTPS + 备案域名、多 worker、限流改 Redis；多实例部署前先跑迁移脚本，见使用手册 Q5b）

## 测试

```bash
cd backend
python -m pytest tests/ -q        # 60 条离线单测：金额解析、记忆预算、AI 接口归属隔离与幂等，不碰库不烧模型
python scripts/smoke_ai.py        # AI 应用四阶段冒烟（真实库 + 真实 glm-4-flash）
python scripts/e2e_flows.py       # A/B/C/D 业务流端到端：创作→发布回填 / 账单→报告 / 计划→确认节省（幂等）/ 审核
```

小程序页面自动化（需先在开发者工具「设置→安全设置」开启服务端口）：

```bash
"微信开发者工具/cli.bat" auto --project frontend --auto-port 9420
node .auto-test/verify_pages.js   # 25 项真实点击/断言/截图，结果与截图在 .auto-test/
```

## 安全提示

上线前必须：改掉 `.env` 的 `SECRET_KEY` 默认值、改管理后台默认口令 `admin/admin123`。
`.env` 已在 `.gitignore` 中，提交前 `git status` 再确认一次。

## License

MIT
