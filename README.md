# 基于大语言模型的省钱攻略智能推荐平台

> 微信小程序名：**省活攻略** — 一个帮你省钱、记账、薅羊毛的 AI 智能助手小程序，让每一分钱都花在刀刃上。

## 核心功能

### AI 省钱助手（亮点功能）
- **购物比价建议**：告诉 AI 你想买什么，它帮你分析值不值得买、什么时候买最便宜
- **省钱菜谱生成**：告诉 AI 冰箱里有什么食材，它帮你生成菜谱并估算成本
- **账单智能分析**：把消费记录发给 AI，它自动分类、找出冲动消费、给出省钱建议
- **省钱知识问答**：基于省钱攻略知识库，回答各种「怎么省」的问题

### 其他功能
- **省钱攻略文章**：精选省钱技巧文章，分类浏览，支持点赞收藏
- **省钱社区**：用户分享省钱经验，发帖、评论、点赞
- **账单记账**：记录每日消费，自动分类，月度消费报表
- **省钱打卡**：设定月度省钱目标，每天打卡记录，进度可视化

## 技术架构

| 层 | 技术 |
|------|------|
| 前端 | 微信小程序（原生开发） |
| 后端 | Python FastAPI + MySQL |
| AI 智能体 | 大语言模型 + Function Calling（多工具协作） |
| 知识库 | RAG 向量检索（ChromaDB） |
| 大模型 | 阿里云 DashScope（通义千问 qwen-turbo） |

## 项目结构

```
cangku/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用入口
│   │   ├── core/               # 核心配置
│   │   │   ├── config.py       # 配置（读取 .env 环境变量）
│   │   │   ├── database.py     # 数据库连接
│   │   │   └── security.py     # JWT 鉴权
│   │   ├── models/             # 数据库模型（10 张表）
│   │   ├── schemas/            # 请求/响应数据模型
│   │   ├── api/routes/         # API 路由
│   │   │   ├── auth.py         # 用户认证
│   │   │   ├── articles.py     # 攻略文章
│   │   │   ├── posts.py        # 社区帖子
│   │   │   ├── agent.py        # AI 助手
│   │   │   ├── bills.py        # 账单管理
│   │   │   └── checkin.py      # 省钱打卡
│   │   ├── agent/              # AI 智能体核心
│   │   │   ├── engine.py       # Agent 编排引擎
│   │   │   ├── llm.py          # 大模型调用封装
│   │   │   ├── memory.py       # 对话记忆管理
│   │   │   └── tools/          # Agent 工具集
│   │   ├── services/           # 业务逻辑层
│   │   └── utils/              # 工具函数
│   ├── .env.example            # 环境变量模板（复制为 .env 填写）
│   └── requirements.txt        # Python 依赖
│
└── frontend/                   # 微信小程序前端
    └── miniprogram/
        ├── app.js              # 全局逻辑（baseUrl 配置在此）
        ├── app.json            # 页面路由、tabBar 配置
        ├── pages/              # 9 个页面
        │   ├── index/          # 首页（攻略文章）
        │   ├── community/      # 社区
        │   ├── assistant/      # AI 助手
        │   ├── bill/           # 账单
        │   ├── mine/           # 我的
        │   ├── login/          # 登录
        │   ├── articleDetail/  # 文章详情
        │   ├── postDetail/     # 帖子详情
        │   └── postCreate/     # 发帖
        └── utils/              # 工具函数（请求封装等）
```

## 快速开始

### 环境要求

- Python 3.10+
- MySQL 8.0+
- 微信开发者工具（最新稳定版）

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/你的仓库名.git
cd 你的仓库名
```

### 2. 配置后端

```bash
# 进入后端目录
cd backend

# 创建数据库
mysql -u root -p
# 在 MySQL 中执行：
# CREATE DATABASE fastapi_db DEFAULT CHARSET utf8mb4;
# exit;

# 复制环境变量模板，填入你的真实配置
cp .env.example .env
# 编辑 .env，填入数据库密码、API Key 等

# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --reload --port 8000
```

启动成功后访问 http://localhost:8000/docs 查看 API 文档。

### 3. 配置 `.env` 文件

复制 `.env.example` 为 `.env`，填入以下内容：

```env
DATABASE_URL=mysql+pymysql://root:你的数据库密码@localhost:3306/fastapi_db

LLM_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
LLM_API_KEY=sk-你的阿里云API密钥
LLM_MODEL=qwen-turbo

SECRET_KEY=随机生成的字符串

WX_APPID=你的小程序appid
WX_SECRET=你的小程序secret
```

> **安全提示**：`.env` 文件已被 `.gitignore` 忽略，不会上传到 GitHub。

### 4. 获取大模型 API Key

本项目默认使用阿里云 DashScope（通义千问），也可替换为其他兼容 OpenAI 接口的大模型。

**阿里云 DashScope（推荐，免费额度充足）：**
1. 访问 https://dashscope.aliyun.com/
2. 阿里云账号登录（支付宝扫码即可）
3. 点「API-KEY」→「创建」
4. 复制以 `sk-` 开头的字符串填入 `.env`

免费额度：每个模型 100 万 tokens/月。

### 5. 配置小程序前端

1. 打开微信开发者工具
2. 点击「导入项目」，目录选择 `frontend/`
3. AppID 填你的小程序 AppID，或选「测试号」
4. 在 `miniprogram/app.js` 中确认 `baseUrl` 为 `http://localhost:8000`
5. 开发者工具右上角「详情」→「本地设置」→ 勾选「不校验合法域名...」
6. 点击「编译」即可在模拟器中预览

### 6. 手机预览

1. 确保后端服务正在运行
2. 开发者工具顶部点「预览」，生成二维码
3. 手机微信扫码预览
4. 手机和电脑需在同一 WiFi 下，且 `baseUrl` 改为电脑局域网 IP（cmd 输入 `ipconfig` 查看 IPv4 地址）

## API 接口

| 模块 | 路径 | 说明 |
|------|------|------|
| 用户认证 | `/auth/login` | 微信登录，返回 JWT token |
| 用户信息 | `/auth/me` | 获取当前登录用户 |
| 攻略文章 | `/articles` | 文章列表/详情 |
| 社区帖子 | `/posts` | 发帖/评论/点赞 |
| AI 助手 | `/agent/chat` | Agent 对话（多工具协作） |
| 账单管理 | `/bills` | 账单增删查/月度汇总 |
| 省钱打卡 | `/checkin` | 打卡记录/目标进度 |

完整接口文档：启动后端后访问 http://localhost:8000/docs

## AI Agent 工具说明

| 工具 | 功能 | 示例输入 |
|------|------|---------|
| generate_recipe | 根据食材生成省钱菜谱 | "土豆、鸡蛋、青椒" |
| shopping_advice | 商品购买建议与比价 | "2000元扫地机器人" |
| analyze_bills | 消费记录分析与省钱建议 | 本月账单数据 |
| search_knowledge | 省钱知识库问答 | "怎么省外卖费" |

Agent 引擎通过 Function Calling 自动选择合适工具，支持多轮对话。

## 使用场景示例

**场景 1：购物前咨询**
> 用户：我想买个 2000 元左右的扫地机器人，家里有猫
> AI：追问房屋面积后，给出推荐型号、历史最低价、最佳下单时机

**场景 2：不知道做什么菜**
> 用户：冰箱里有土豆、青椒、鸡蛋
> AI：推荐 3 道菜（青椒土豆丝、土豆鸡蛋饼、青椒炒蛋），附做法和成本估算

**场景 3：月度消费复盘**
> 用户：查看本月账单分析
> AI：自动分类（餐饮 450 元、日用品 300 元），指出冲动消费，给出下月建议

## 常见问题

<details>
<summary><b>Q: pip install 报错怎么办？</b></summary>

用国内镜像加速：
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```
</details>

<details>
<summary><b>Q: 启动后端报错 "Can't connect to MySQL"</b></summary>

1. 检查 MySQL 服务是否启动（Win+R → services.msc → 找到 MySQL）
2. 检查 `.env` 中 `DATABASE_URL` 的密码是否正确
3. 确认数据库 `fastapi_db` 已创建
</details>

<details>
<summary><b>Q: 小程序页面空白或 "request fail"</b></summary>

1. 确认后端正在运行（看到 "Uvicorn running"）
2. 确认开发者工具勾选了「不校验合法域名」
3. 确认 `app.js` 中 `baseUrl` 地址正确
</details>

<details>
<summary><b>Q: AI 助手不回复或报错</b></summary>

1. 检查 `.env` 中 `LLM_API_KEY` 是否正确
2. 去 DashScope 官网确认免费额度是否用完
3. 查看后端控制台报错信息
</details>

<details>
<summary><b>Q: 数据库表没建出来？</b></summary>

后端启动时会自动建表（`Base.metadata.create_all`）。如果没有建表：
1. 确认数据库 `fastapi_db` 已创建
2. 重启后端服务
3. 登录 MySQL 检查：`USE fastapi_db; SHOW TABLES;`
</details>

<details>
<summary><b>Q: 手机预览连不上后端？</b></summary>

手机和电脑需在同一 WiFi，且 `app.js` 中 `baseUrl` 改为电脑 IP（不能用 localhost）：
```js
baseUrl: 'http://192.168.1.105:8000'
```
查看 IP：cmd 输入 `ipconfig`，找到 IPv4 地址。
</details>

## 环境变量说明

| 变量 | 说明 | 必填 |
|------|------|------|
| `DATABASE_URL` | MySQL 连接字符串 | 是 |
| `LLM_API_URL` | 大模型 API 地址 | 是 |
| `LLM_API_KEY` | 大模型 API 密钥 | 是 |
| `LLM_MODEL` | 模型名称（默认 qwen-turbo） | 否 |
| `SECRET_KEY` | JWT 签名密钥（随机字符串） | 是 |
| `WX_APPID` | 微信小程序 AppID | 否* |
| `WX_SECRET` | 微信小程序 AppSecret | 否* |

> *开发阶段可用简化登录（code 直接当 openid），无需配置 WX_APPID/WX_SECRET。

## 项目进度

### 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| 后端框架 | ✅ 完成 | FastAPI + SQLAlchemy + MySQL，6 个路由模块 |
| 数据库建模 | ✅ 完成 | 10 张表（用户、文章、帖子、账单、打卡、评论等），启动自动建表 |
| 用户认证 | ✅ 完成 | 微信登录 + JWT 鉴权，token 持久化存储 |
| AI Agent 引擎 | ✅ 完成 | 多工具协作（Function Calling），对话记忆管理 |
| AI 工具 - 菜谱生成 | ✅ 完成 | 根据食材生成省钱菜谱 + 成本估算 |
| AI 工具 - 购物建议 | ✅ 完成 | 商品分析与购买建议 |
| AI 工具 - 账单分析 | ✅ 完成 | 消费分类 + 冲动消费识别 + 省钱建议 |
| AI 工具 - 知识问答 | ✅ 完成 | RAG 向量检索（ChromaDB）省钱知识库 |
| 前端页面 | ✅ 完成 | 9 个页面全部实现（首页/社区/AI助手/账单/我的/登录/文章详情/帖子详情/发帖） |
| 攻略文章模块 | ✅ 完成 | 文章列表/详情/点赞，后端接口已通 |
| 社区帖子模块 | ✅ 完成 | 发帖/详情/评论/点赞 |
| 账单模块 | ✅ 完成 | 账单增删查 + 月度分类汇总 |
| 省钱打卡 | ✅ 完成 | 打卡记录 + 目标进度 |
| 环境变量管理 | ✅ 完成 | .env 配置 + .env.example 模板，密钥不上传 GitHub |

### 待完善

| 模块 | 状态 | 说明 |
|------|------|------|
| tabBar 图标 | ⏳ 待做 | 目前只有文字，需添加图标资源 |
| RAG 知识库数据 | ⏳ 待做 | 需导入省钱攻略示例数据 |
| 账单录入 UI | ⏳ 待做 | 目前只有 Toast 提示，需实现录入弹窗 |
| 消费报表可视化 | ⏳ 待做 | 月度消费饼图/趋势图 |
| 微信真实登录 | ⏳ 待做 | 当前为简化方案（code 当 openid），需对接微信 API |
| 生产部署 | ⏳ 待做 | 文档编写 + 前端打包 + 域名配置 |

## License

MIT
