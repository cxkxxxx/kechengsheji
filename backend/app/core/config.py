import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 未安装时用默认值

# 数据库连接
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/fastapi_db",
)

# 大模型 API
# 默认对接智谱 AI（.env 里就是这套）；换成任意 OpenAI 兼容服务只改这三个变量
#   智谱     https://open.bigmodel.cn/api/paas/v4/chat/completions   glm-4-flash
#   阿里云   https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions  qwen-turbo
LLM_API_URL = os.getenv(
    "LLM_API_URL",
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flash")
# 视觉多模态模型：用于"上传图片让AI看懂"，可通过 .env 覆盖
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", "glm-4v-flash")

# 图片上传目录（存放用户/聊天里上传的图片）
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./static/uploads")
# 常用模型参考：
#   glm-4-flash   ：智谱免费档，支持 Function Calling（默认）
#   glm-4-plus    ：智谱付费档，更强
#   qwen-turbo    ：阿里云 DashScope，改 LLM_API_URL + LLM_MODEL 即可
# 图片理解走 LLM_VISION_MODEL，须与 LLM_API_URL 属于同一家服务

# 单次回复的 token 上限。600 会把长菜谱截断在第三条中途（实测 finish_reason=length），
# 1200 时同样内容用 834 tokens 正常收尾
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1200"))

# JWT 鉴权
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天

# RAG 向量库路径
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")

# AI 接口限流（每个用户每分钟允许的对话/记账类大模型调用次数）
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

# 微信小程序配置（用于 code 换 openid）
WX_APPID = os.getenv("WX_APPID", "")
WX_SECRET = os.getenv("WX_SECRET", "")

# ===== 图片上传（社区帖子 / 攻略投稿 / AI 助手识图共用）=====
# 单张上限。/static 是公开可直接访问的目录，所以只收真正的图片字节流，
# 扩展名由服务端按魔数决定，不信客户端传来的文件名。
UPLOAD_MAX_MB = float(os.getenv("UPLOAD_MAX_MB", "2"))
UPLOAD_MAX_BYTES = int(UPLOAD_MAX_MB * 1024 * 1024)
# 条数上限在落库前校验，前端选图时也各拦一道
POST_MAX_IMAGES = int(os.getenv("POST_MAX_IMAGES", "9"))
ARTICLE_MAX_IMAGES = int(os.getenv("ARTICLE_MAX_IMAGES", "4"))   # 1 封面 + 3 配图

# ===== 商品比价 =====
# 实时价走 best-price-mcp（京东/天猫），它不需要任何密钥、装好包就能用，
# 但数据源是第三方中转、有共享日配额，所以查不到时会自动降级到
# 站内 price_history 价格库 + 各平台搜索直达链接。
# 外部接口超时（秒）。宁可降级也不要让 AI 对话卡在这
PRICE_TIMEOUT = float(os.getenv("PRICE_TIMEOUT", "8"))