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

# 大模型 API - 当前使用：阿里云 DashScope（通义千问）
# 获取地址：https://dashscope.aliyun.com/
# 免费额度：每个模型每月 100 万 tokens
LLM_API_URL = os.getenv(
    "LLM_API_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-turbo")
# 视觉多模态模型：用于"上传图片让AI看懂"，可通过 .env 覆盖
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", "glm-4v-flash")

# 图片上传目录（存放用户/聊天里上传的图片）
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./static/uploads")
# 可用模型说明：
#   qwen-turbo   ：速度快，免费 100万 tokens/月（推荐默认）
#   qwen-plus    ：能力更强，免费 100万 tokens/月
#   qwen-max     ：最强模型，免费额度有限
#   qwen-long    ：长文本，适合知识库

# JWT 鉴权
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天

# RAG 向量库路径
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")

# API 限流
RATE_LIMIT_PER_MINUTE = 10

# 微信小程序配置（用于 code 换 openid）
WX_APPID = os.getenv("WX_APPID", "")
WX_SECRET = os.getenv("WX_SECRET", "")